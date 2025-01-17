import logging
import usb
import usb.backend.libusb0 as libusb0

log = logging.getLogger(__name__)

from .DeviceID import DeviceID

##
# Generates a list of DeviceID objects for all connected USB Wasatch Photonics 
# spectrometers.
class DeviceFinderUSB(object):

    WASATCH_VID = 0x24aa
    OCEAN_VID = 0x2457
    ANDOR_VID = 0x136e
    FT232_SPI_VID = 0x0403
    WP_HAMA_SILICON_PID = 0x1000
    WP_HAMA_INGAAS_PID = 0x2000
    WP_ARM_PID = 0x4000

    def __init__(self):
        pass

    ##
    # Iterates over each supported PID, searching for any Wasatch devices
    # with a known VID/PID and generating a list of DeviceIDs.
    #
    # Note that DeviceID internally pulls more attributes from the Device object.
    # def find_usb_devices_alternate_unused(self):
    #     vid = 0x24aa
    #     device_ids = []
    #     count = 0
    #     for pid in [0x1000, 0x2000, 0x4000]:
    #         # we could also remove iProduct and do one find on vid
    #         devices = usb.core.find(find_all=True, idVendor=vid, idProduct=pid)
    #         for device in devices:
    #             count += 1
    #             log.debug("DeviceListFID: discovered vid 0x%04x, pid 0x%04x (count %d)", vid, pid, count)
    #
    #             device_id = DeviceID(device=device)
    #             device_ids.append(device_id)
    #     return device_ids
    
    ##
    # Iterates over each USB bus, and each device on the bus, retaining any
    # with a Wasatch Photonics VID and supported PID and instantiating a
    # DeviceID for each.  
    #
    # Note that DeviceID internally pulls more attributes from the Device object.
    def find_usb_devices(self):
        device_ids = []
        count = 0
        for device in usb.core.find(find_all=True, backend=libusb0.get_backend()):
            count += 1
            vid = int(device.idVendor)
            pid = int(device.idProduct)
            log.debug("DeviceListFID: discovered vid 0x%04x, pid 0x%04x (count %d)", vid, pid, count)

            if vid not in [self.WASATCH_VID, self.OCEAN_VID, self.ANDOR_VID, self.FT232_SPI_VID]:
                continue

            if vid == self.WASATCH_VID and pid not in [ self.WP_HAMA_SILICON_PID, self.WP_HAMA_INGAAS_PID, self.WP_ARM_PID ]:
                continue

            device_id = DeviceID(device=device)
            device_ids.append(device_id)
        return device_ids
