""" Higher level abstractions for devices and communication buses.  Allows for
    the wrapping of simulation devices and real hardware devices simultaneously.

    TODO: split into single-class files.
"""

import time
import numpy
import Queue
import logging
import multiprocessing

from ConfigParser import ConfigParser

from . import simulation_protocol
from . import common
from . import utils

from FeatureIdentificationDevice import FeatureIdentificationDevice
from StrokerProtocolDevice       import StrokerProtocolDevice
from SpectrometerSettings        import SpectrometerSettings
from SpectrometerState           import SpectrometerState
from ControlObject               import ControlObject
from WasatchBus                  import WasatchBus
from Reading                     import Reading

log = logging.getLogger(__name__)

class WasatchDevice(object):
    """ Provide an interface to the actual libusb bus.  The summary object is
        used in order to pass just a simple python object on the multiprocessing
        queue instead of an entire device object. Passing the entire device
        object caused problems on Windows.

        MZ: some of these methods are called from MainProcess, others by
        subprocess. """

    def __init__(self, uid=None, bus_order=0, tolerant=True):
        super(WasatchDevice, self).__init__()
        log.debug("%s setup", self.__class__.__name__)

        self.uid = uid
        self.bus_order = bus_order
        self.tolerant = tolerant
        self.connected = False

        self.command_queue = multiprocessing.Queue() # routes ENLIGHTEN 'change settings' commands to the spectrometer process
        self.backend_error = 0

        control_object = ControlObject("integration_time_ms", 10)
        self.command_queue.put(control_object)

        self.settings = SpectrometerSettings()

        self.summed_spectra         = None
        self.sum_count              = 0
        self.session_reading_count  = 0

    def connect(self):
        """ Attempt low level connection to the device specified in init.  """
        # if self.uid == "0x24aa:0x0512":
        #     log.info("Connected to SimulationMevice")
        #     self.hardware = simulation_protocol.SimulateMaterial()
        #     self.connected = True
        #     self.initialize_settings()
        #     return True

        if self.connect_feature_identification():
            log.info("Connected to FeatureIdentificationDevice")
            self.connected = True
            self.initialize_settings()
            return True

        if self.connect_stroker_protocol():
            log.info("Connected to StrokerProtocolDevice")
            self.connected = True
            self.initialize_settings()
            return True

        log.debug("Can't find FID or SP class device")

        return False

    def connect_stroker_protocol(self):
        """ Given a specified universal identifier, attempt to connect to the device using stroker protocol. """
        FID_list = ["0x1000", "0x2000", "0x3000", "0x4000"]

        if self.uid == None:
            log.debug("No specified UID for stroker protocol connect")
            return False

        if any(fid in self.uid for fid in FID_list):
            log.debug("Compatible feature ID not found")
            return False

        if self.backend_error >= 1:
            if self.backend_error == 2:
                log.warn("Don't attempt to connect with no backend")
            return

        # MZ: what is self.uid?
        dev = None
        try:
            bus_pid = self.uid[7:]
            log.info("Attempt connection to: %s", bus_pid)

            dev = StrokerProtocolDevice(pid=bus_pid)
            result = dev.connect()
            if result != True:
                log.critical("Low level failure in device connect")
                return False
            self.hardware = dev

        except Exception as exc:
            log.critical("Problem connecting to: %s", self.uid, exc_info=1)
            return False

        log.info("Connected to StrokerProtocolDevice %s", self.uid)
        return True

    def connect_feature_identification(self):
        """ Given a specified universal identifier, attempt to connect to the
            device using feature identification firmware. """
        FID_list = ["0x1000", "0x2000", "0x3000", "0x4000"]

        if self.uid == None:
            log.debug("No specified UID for feature id connect")
            return False

        if not any(fid in self.uid for fid in FID_list):
            log.debug("Compatible feature ID not found")
            return False

        if self.backend_error >= 1:
            if self.backend_error == 2:
                log.warn("Don't attempt to connect with no backend")
            return

        dev = None
        try:
            bus_pid = self.uid[7:]
            log.debug("connect_fid: Attempt connection to bus_pid %s (bus_order %d)", bus_pid, self.bus_order)

            dev = FeatureIdentificationDevice(pid=bus_pid, bus_order=self.bus_order)
            result = False

            try:
                result = dev.connect()
            except Exception as exc:

                # MZ: what is this? we retry with bus_order 0, PID 0x2000?
                log.critical("Connect level exception: %s", exc, exc_info=1)
                dev = FeatureIdentificationDevice(pid="0x2000", bus_order=0)
                try:
                    result = dev.connect()
                except Exception as exc:
                    log.critical("SECOND Level exception: %s", exc)

            if result != True:
                log.critical("Low level failure in device connect")
                return False
            self.hardware = dev

        except Exception as exc:
            log.critical("Problem connecting to: %s", self.uid, exc_info=1)
            return False

        log.info("Connected to FeatureIdentificationDevice %s", self.uid)
        return True

    def initialize_settings(self):
        if self.connected == False:
            return

        self.settings = self.hardware.settings

        # generic post-initialization stuff for both SP and FID
        self.hardware.get_microcontroller_firmware_version()
        self.hardware.get_fpga_firmware_version()
        self.hardware.get_integration_time()
        self.hardware.get_ccd_gain()

        # could read the defaults for these ss.state volatiles from FID/SP too:
        #
        # self.tec_setpoint_degC
        # self.high_gain_mode_enabled
        # self.triggering_enabled
        # self.laser_enabled
        # self.laser_power_perc
        # self.ccd_offset

        self.settings.update_wavecal()
        self.settings.dump()

    def disconnect(self):
        log.info("WasatchDevice.disconnect: calling hardware disconnect")
        try:
            self.hardware.disconnect()
            # MZ: should this not update the bus, which is checked by control.connect_new?
        except Exception as exc:
            log.critical("Issue disconnecting hardware", exc_info=1)

        time.sleep(0.1)
        return True

    # Assumes bad_pixels is a sorted array (possibly empty)
    def correct_bad_pixels(self, spectrum):

        if not self.settings or not self.settings.eeprom or not self.settings.eeprom.bad_pixels:
            return

        if not spectrum:
            return

        pixels = len(spectrum)
        bad_pixels = self.settings.eeprom.bad_pixels

        # iterate over each bad pixel
        i = 0
        while i < len(bad_pixels):

            bad_pix = bad_pixels[i]

            if bad_pix == 0:
                # handle the left edge
                next_good = bad_pix + 1
                while next_good in bad_pixels and next_good < pixels:
                    next_good += 1
                    i += 1
                if next_good < pixels:
                    for j in range(next_good):
                        spectrum[j] = spectrum[next_good]
            else:

                # find previous good pixel
                prev_good = bad_pix - 1
                while prev_good in bad_pixels and prev_good >= 0:
                    prev_good -= 1

                if prev_good >= 0:
                    # find next good pixel
                    next_good = bad_pix + 1
                    while next_good in bad_pixels and next_good < pixels:
                        next_good += 1
                        i += 1

                    if next_good < pixels:
                        # for now, draw a line between previous and next good pixels
                        # TODO: consider some kind of curve-fit
                        delta = float(spectrum[next_good] - spectrum[prev_good])
                        rng   = next_good - prev_good
                        step  = delta / rng
                        for j in range(rng - 1):
                            # MZ: examining performance
                            # spectrum[prev_good + j + 1] = spectrum[prev_good] + step * (j + 1)
                            spectrum[prev_good + j + 1] = spectrum[prev_good] + int(step * (j + 1))
                    else:
                        # we ran off the high end, so copy-right
                        for j in range(bad_pix, pixels):
                            spectrum[j] = spectrum[prev_good]

            # advance to next bad pixel
            i += 1

    # MZ: This is akin to getSpectrum() in other drivers.  Can be called directly
    #     in a blocking interface, or from subprocess in non-blocking queued architecture.
    #     Note that subprocess.acquire_data() takes a common.acquisition_mode argument,
    #     where this does not.
    def acquire_data(self):
        """ Process all enqueued settings, then read actual data from the device.

            Notes:
                - we always return raw readings, even during scan averaging (.spectrum)
                - if averaging was enabled and we're complete, then we return the
                  averaged "complete" INSTEAD OF the raw
                - we always return temperatures for live GUI updates
                - we always perform bad pixel correction

                - currently returning INTEGRAL averages (including bad_pixel)
        """

        log.debug("Device acquire_data")

        # yes, allow settings to change in the midst of a long average; this way
        # they can turn off laser, disable averaging etc
        self.process_commands()

        averaging_enabled = (self.settings.state.scans_to_average > 1)

        # start a new reading
        reading = Reading()

        # TODO...just include a copy of SpectrometerState? something to think about
        # That would actually provide a reason to roll all the temperature etc readouts
        # into the SpectrometerState class...
        reading.integration_time_ms = self.settings.state.integration_time_ms
        reading.laser_enabled       = self.settings.state.laser_enabled
        reading.laser_power_perc    = self.settings.state.laser_power_perc

        # collect next spectrum
        try:
            reading.spectrum = self.hardware.get_line()

            log.debug("device.acquire_data: got %s ...", reading.spectrum[0:9])

            # bad pixel correction
            if self.settings.state.bad_pixel_mode == SpectrometerState.BAD_PIXEL_MODE_AVERAGE:
                self.correct_bad_pixels(reading.spectrum)

            log.debug("device.acquire_data: after bad_pixel correction: %s ...", reading.spectrum[0:9])

            # update summed spectrum
            if averaging_enabled:
                if self.sum_count == 0:
                    self.summed_spectra = numpy.array([float(i) for i in reading.spectrum])
                else:
                    log.debug("device.acquire_data: summing spectra")
                    self.summed_spectra = numpy.add(self.summed_spectra, reading.spectrum)
                self.sum_count += 1
                log.debug("device.acquire_data: summed_spectra : %s ...", self.summed_spectra[0:9])

        except Exception as exc:
            log.critical("Error reading hardware data", exc_info=1)
            reading.failure = exc

        # count spectra
        self.session_reading_count += 1
        reading.session_count = self.session_reading_count
        reading.sum_count = self.sum_count

        # read detector temperature if applicable (should we do this for Ambient as well?)
        if True or self.settings.eeprom.has_cooling:
            try:
                reading.detector_temperature_raw  = self.hardware.get_detector_temperature_raw()
                reading.detector_temperature_degC = self.hardware.get_detector_temperature_degC(reading.detector_temperature_raw)
            except Exception as exc:
                if not self.tolerant:
                    log.critical("Error reading detector temperature", exc_info=1)
                    reading.failure = exc
                else:
                    log.debug("Error reading detector temperature", exc_info=1)

        # only read laser temperature if we have a laser (how do we determine this for StrokerProtocol?)
        if self.settings.eeprom.has_laser:
            try:
                count = 2 if self.settings.state.secondary_adc_enabled else 1
                for throwaway in range(count):
                    reading.laser_temperature_raw  = self.hardware.get_laser_temperature_raw()
                reading.laser_temperature_degC = self.hardware.get_laser_temperature_degC(reading.laser_temperature_raw)
            except Exception as exc:
                if self.tolerant:
                    log.debug("Error reading laser temperature", exc_info=1)
                else:
                    log.critical("Error reading laser temperature", exc_info=1)
                    reading.failure = exc

        # read secondary ADC if requested
        if self.settings.state.secondary_adc_enabled:
            try:
                self.hardware.select_adc(1)
                for throwaway in range(2):
                    reading.secondary_adc_raw = self.hardware.get_secondary_adc_raw()
                reading.secondary_adc_calibrated = self.hardware.get_secondary_adc_calibrated(reading.secondary_adc_raw)
                self.hardware.select_adc(0)
            except Exception as exc:
                if self.tolerant:
                    log.debug("Error reading secondary ADC", exc_info=1)
                else:
                    log.critical("Error reading secondary ADC", exc_info=1)
                    reading.failure = exc

        # have we completed the averaged reading?
        if averaging_enabled:
            if self.sum_count >= self.settings.state.scans_to_average:
                # if we wanted to send the averaged spectrum as ints, use numpy.ndarray.astype(int)
                reading.spectrum = numpy.divide(self.summed_spectra, self.sum_count).tolist()
                log.debug("device.acquire_data: averaged_spectrum : %s ...", reading.spectrum[0:9])
                reading.averaged = True

                # reset for next average
                self.summed_spectra = None
                self.sum_count = 0

        return reading

    # MZ: called by acquire_data, ergo subprocess
    def process_commands(self):
        """ Process every entry on the settings queue, write them to the
            device. Failures when writing settings are collected by this
            exception handler. """

        control_object = "throwaway"
        while control_object != None:
            try:
                control_object = self.command_queue.get_nowait()
                log.debug("process_commands: %s -> %s", control_object.setting, control_object.value)
                self.hardware.write_setting(control_object)
            except Queue.Empty:
                log.debug("process_commands: queue empty")
                control_object = None
            except Exception as exc:
                log.critical("process_commands: error dequeuing or writing control object", exc_info=1)
                raise

    # called by subprocess.continuous_poll
    def change_setting(self, setting, value):
        """ Add the specified setting and value to the local control queue. """
        log.debug("WasatchDevice.change_setting: %s -> %s", setting, value)
        control_object = ControlObject(setting, value)

        if control_object.setting == "scans_to_average":
            self.sum_count = 0

        try:
            self.command_queue.put(control_object)
        except Exception as exc:
            log.critical("WasatchDevice.change_setting: can't enqueue %s -> %s",
                setting, value, exc_info=1)