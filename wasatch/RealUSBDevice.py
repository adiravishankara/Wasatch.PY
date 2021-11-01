import usb
import logging
from .AbstractUSBDevice import AbstractUSBDevice

log = logging.getLogger(__name__)

class RealUSBDevice(AbstractUSBDevice):

    def __init__(self):
        pass

    def find(self, *args, **kwargs):
        return usb.core.find(*args, **kwargs)

    def set_configuration(self, device):
        device.set_configuration()

    def reset(self, dev):
        dev.reset()

    def claim_interface(self):
        return usb.util.claim_interface(*args, **kwargs)

    def release_interface(self, *args, **kwargs):
        return usb.util.release_interface(*args, **kwargs)

    def ctrl_transfer(self, *args):
        device = args[0]
        ctrl_args = args[1:]
        return device.ctrl_transfer(*ctrl_args)

    def read(self, *args, **kwargs):
        device =  args[0]
        read_args = args[1:]
        return device.read(*read_args, **kwargs)

    def send_code(self):
        pass