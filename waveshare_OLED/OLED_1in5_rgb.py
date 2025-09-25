#!/usr/bin/env python3
from . import config
import time
from PIL import Image
import numpy as np

Device_SPI = config.Device_SPI
Device_I2C = config.Device_I2C

OLED_WIDTH   = 128
OLED_HEIGHT  = 128

class OLED_1in5_rgb(config.RaspberryPi):
    """Driver for the Waveshare 1.5\" RGB SSD1351 display over SPI."""

    def command(self, cmd: int):
        self.digital_write(self.DC_PIN, False)
        self.spi_writebyte([cmd])

    def data(self, byte: int):
        self.digital_write(self.DC_PIN, True)
        self.spi_writebyte([byte])

    def Init(self):
        if self.module_init() != 0:
            return -1

        self.width  = OLED_WIDTH
        self.height = OLED_HEIGHT
        self.reset()

        if self.Device == Device_I2C:
            print("Only Device_SPI is supported; please revise config.py")
            exit()

        # Initialization sequence (same as before)
        seq = [
            (0xfd, [0x12]), (0xfd, [0xB1]),
            (0xae, []),   (0xa4, []),
            (0x15, [0x00, 0x7f]), (0x75, [0x00, 0x7f]),
            (0xB3, [0xF1]), (0xCA, [0x7F]),
            (0xa0, [0x74]), (0xa1, [0x00]),
            (0xa2, [0x00]), (0xAB, [0x01]),
            (0xB4, [0xA0, 0xB5, 0x55]),
            (0xC1, [0xC8, 0x80, 0xC0]),
            (0xC7, [0x0F]), (0xB1, [0x32]),
            (0xB2, [0xA4, 0x00, 0x00]),
            (0xBB, [0x17]), (0xB6, [0x01]),
            (0xBE, [0x05]), (0xA6, []),
        ]
        for cmd, args in seq:
            self.command(cmd)
            for b in args:
                self.data(b)

        time.sleep(0.1)
        self.command(0xAF)
        return 0

    def reset(self):
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.1)
        self.digital_write(self.RST_PIN, False)
        time.sleep(0.1)
        self.digital_write(self.RST_PIN, True)
        time.sleep(0.1)

    def clear(self):
        buf = [0x00] * (self.width * self.height * 2)
        self.ShowImage(buf)

    def getbuffer(self, image: Image.Image) -> list[int]:
        im = image.convert("RGB")
        pix = im.load()
        buf = [0] * (self.width * self.height * 2)
        idx = 0
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = pix[x, y]
                buf[idx]     = ((r & 0xF8) | (g >> 5)) & 0xFF
                buf[idx + 1] = (((g << 3) & 0xE0) | (b >> 3)) & 0xFF
                idx += 2
        return buf

    def ShowImage(self, pBuf: list[int]):
        # 1) set column window 0→127
        self.command(0x15)
        self.data(0x00)
        self.data(0x7F)

        # 2) set row window 0→127
        self.command(0x75)
        self.data(0x00)
        self.data(0x7F)

        # 3) RAM write command + data mode
        self.command(0x5C)
        self.digital_write(self.DC_PIN, True)

        # 4) send entire buffer in large chunks
        CHUNK = 4096
        for i in range(0, len(pBuf), CHUNK):
            self.spi_writebyte(pBuf[i:i+CHUNK])

        # 5) back to command mode
        self.digital_write(self.DC_PIN, False)
        return
