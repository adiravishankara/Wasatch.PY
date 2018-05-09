import datetime
import logging

log = logging.getLogger(__name__)

class Reading(object):
    """ A single set of data read from a device. This includes spectrum,
        temperature, gain, offset, etc. Essentially a snapshot of the device
        state in time. """

    def __init__(self):
        super(Reading, self).__init__()
        log.debug("%s setup", self.__class__.__name__)

        self.timestamp = datetime.datetime.now()

        # MZ: hardcode
        self.spectrum                  = [0] * 1024
        self.laser_temperature_raw     = 0 # TODO: make this None
        self.laser_temperature_degC    = 0
        self.detector_temperature_raw  = 0
        self.detector_temperature_degC = 0
        self.secondary_adc_raw         = None
        self.secondary_adc_calibrated  = None
        self.laser_status              = None   # make this laser_enabled
        self.laser_power               = 0      # make this laser_power_perc
        self.failure                   = None
        self.averaged                  = False
        self.session_count             = 0

    def dump(self):
        log.info("Reading:")
        log.info("  Spectrum:               %s", self.spectrum[:5])
        log.info("  Laser Temp Raw:         0x%04x", self.laser_temperature_raw)
        log.info("  Laser Temp DegC:        %.2f", self.laser_temperature_degC)
        log.info("  Detector Temp Raw:      0x%04x", self.detector_temperature_raw)
        log.info("  Detector Temp DegC:     %.2f", self.detector_temperature_degC)
        log.info("  2nd ADC Raw:            %s", None if self.secondary_adc_raw is None else "0x%04x" % self.secondary_adc_raw)
        log.info("  2nd ADC Calibrated:     %s", None if self.secondary_adc_calibrated is None else "%.2f" % self.secondary_adc_calibrated)
        log.info("  Laser Status:           %s", self.laser_status)
        log.info("  Laser Power:            %d", self.laser_power)
        log.info("  Failure:                %s", self.failure)
        log.info("  Averaged:               %s", self.averaged)
        log.info("  Session Count:          %d", self.session_count)