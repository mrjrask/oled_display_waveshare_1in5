import time
from smbus import SMBus
import spidev
from gpiozero import DigitalOutputDevice, DigitalInputDevice

Device_SPI = 1
Device_I2C = 0

class RaspberryPi:
    def __init__(
        self,
        spi=None,
        spi_freq: int = 30000000,   # 30 MHz by default
        rst: int = 27,
        dc: int = 25,
        bl: int = 18,
        bl_freq: int = 1000,
        i2c=None
    ):
        self.INPUT = False
        self.OUTPUT = True
        self.SPEED  = spi_freq

        if Device_SPI == 1:
            self.Device = Device_SPI
            # allow passing in custom spidev, or default to CE0
            self.spi = spi if spi else spidev.SpiDev(0, 0)
        else:
            self.Device = Device_I2C
            self.address = 0x3c
            self.bus = SMBus(1)

        self.RST_PIN = self.gpio_mode(rst, self.OUTPUT)
        self.DC_PIN  = self.gpio_mode(dc,  self.OUTPUT)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def gpio_mode(self, Pin, Mode, pull_up=None, active_state=True):
        if Mode:
            return DigitalOutputDevice(Pin, active_high=True, initial_value=False)
        else:
            return DigitalInputDevice(Pin, pull_up=pull_up, active_state=active_state)

    def digital_write(self, Pin, value):
        if value:
            Pin.on()
        else:
            Pin.off()

    def digital_read(self, Pin):
        return Pin.value

    def spi_writebyte(self, data: list[int]):
        """
        Write a sequence of bytes over SPI in one go.
        `data` should be a list of integer byte values.
        """
        self.spi.writebytes(data)

    def i2c_writebyte(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)

    def module_init(self):
        self.digital_write(self.RST_PIN, False)
        if self.Device == Device_SPI:
            self.spi.max_speed_hz = self.SPEED
            self.spi.mode         = 0b11
        self.digital_write(self.DC_PIN, False)
        return 0

    def module_exit(self):
        if self.Device == Device_SPI:
            self.spi.close()
        else:
            self.bus.close()
        self.digital_write(self.RST_PIN, False)
        self.digital_write(self.DC_PIN, False)
