﻿# **************************************************************************************************
#  MIT License                                                                                     *
#                                                                                                  *
#  Copyright (c) 2021 Dietrich Christopeit                                                         *
#                                                                                                  *
#  Permission is hereby granted, free of charge, to any person obtaining a copy                    *
#  of this software and associated documentation files (the "Software"), to deal                   *
#  in the Software without restriction, including without limitation the rights                    *
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell                       *
#  copies of the Software, and to permit persons to whom the Software is                           *
#  furnished to do so, subject to the following conditions:                                        *
#                                                                                                  *
#  The above copyright notice and this permission notice shall be included in all                  *
#  copies or substantial portions of the Software.                                                 *
#                                                                                                  *
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR                      *
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,                        *
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT_TYPE SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************
from abc import abstractmethod
from asyncio import Event
from datetime import datetime

from LegoBTLE.Device.ADevice import Device
from LegoBTLE.LegoWP.messages.downstream import (
    CMD_MOVE_DEV_ABS_POS, CMD_PORT_NOTIFICATION_DEV_REQ,
    CMD_START_MOVE_DEV,
    CMD_START_MOVE_DEV_DEGREES, CMD_START_MOVE_DEV_TIME,
    DOWNSTREAM_MESSAGE,
    )
from LegoBTLE.LegoWP.messages.upstream import (DEV_PORT_NOTIFICATION, DEV_VALUE)


class AMotor(Device):
    
    def port_value_EFF(self):
        return self.port_value.get_port_value_EFF(gearRatio=1.0)

    @property
    @abstractmethod
    def gearRatio(self) -> {float, float}:
        raise NotImplementedError

    @gearRatio.setter
    @abstractmethod
    def gearRatio(self, gearRatio_motor_a: float = 1.0, gearRatio_motor_b: float = 1.0, ) -> {float, float}:
        raise NotImplementedError
    
    @abstractmethod
    async def GOTO_ABS_POS(self, *args) -> CMD_MOVE_DEV_ABS_POS:
        raise NotImplementedError
    
    @abstractmethod
    async def START_SPEED(self, *args) -> CMD_START_MOVE_DEV:
        raise NotImplementedError
    
    @abstractmethod
    async def START_MOVE_DEGREES(self, *args) -> CMD_START_MOVE_DEV_DEGREES:
        raise NotImplementedError
    
    @abstractmethod
    async def START_SPEED_TIME(self, *args) -> CMD_START_MOVE_DEV_TIME:
        raise NotImplementedError
    
    # convenience methods
    
    @property
    @abstractmethod
    def measure_distance_start(self) -> (datetime, {float, float, float}):
        """
        CONVENIENCE METHOD -- This method acts like a stopwatch. It returns the current time and current
        raw "position" of the motor. It can be used to mark the start of an experiment.
        
        :return:
            The current time and raw "position" of the motor
        :rtype: (datetime, {float, float, float})
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def measure_distance_end(self) -> (datetime, {float, float, float}):
        """
        CONVENIENCE METHOD -- This method acts like a stopwatch. It returns the current time and current
        raw "position" of the motor. It can be used to mark the end of an experiment.

        :return:
            The current time and raw "position" of the motor
        :rtype: (datetime, {float, float, float})
        """
        raise NotImplementedError
    
    def distance_start_end(self, gearRatio=1.0) -> {float, float, float}:
        d = {}
        for (k, x1) in self.measure_distance_end[1].items():
            d[k] = (x1 - self.measure_distance_start[1][k]) / gearRatio
        return d
    
    def avg_speed(self, gearRatio=1.0) -> {float, float, float}:
        v = {}
        dt = self.measure_distance_end[0] - self.measure_distance_start[0]
        for (k, d) in self.distance_start_end(gearRatio=gearRatio).items():
            v[k] = d / dt
        return v
