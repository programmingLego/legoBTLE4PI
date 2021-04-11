﻿# coding=utf-8
# **************************************************************************************************
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
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT_TYPE SHALL THE                *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************

"""This class provides the concretions of the most basic baseclass for all attached Devices: ADevice.

The abstract AMotor baseclass models common specifications of a motor.
"""


import asyncio
from abc import abstractmethod
from asyncio import CancelledError
from asyncio import Event
from asyncio import Task
from asyncio import sleep
from collections import defaultdict
from time import monotonic
from typing import Awaitable
from typing import Callable
from typing import Coroutine
from typing import Tuple
from typing import Union
from typing import Optional

import numpy as np

from LegoBTLE.Device.ADevice import Device
from LegoBTLE.LegoWP.messages.downstream import CMD_GOTO_ABS_POS_DEV
from LegoBTLE.LegoWP.messages.downstream import CMD_MODE_DATA_DIRECT
from LegoBTLE.LegoWP.messages.downstream import CMD_SET_ACC_DEACC_PROFILE
from LegoBTLE.LegoWP.messages.downstream import CMD_START_MOVE_DEV_DEGREES
from LegoBTLE.LegoWP.messages.downstream import CMD_START_MOVE_DEV_TIME
from LegoBTLE.LegoWP.messages.downstream import CMD_START_PWR_DEV
from LegoBTLE.LegoWP.messages.downstream import CMD_START_SPEED_DEV
from LegoBTLE.LegoWP.types import C
from LegoBTLE.LegoWP.types import MOVEMENT
from LegoBTLE.LegoWP.types import SI
from LegoBTLE.LegoWP.types import SUB_COMMAND
from LegoBTLE.LegoWP.types import WRITEDIRECT_MODE
from LegoBTLE.networking.prettyprint.debug import debug_info
from LegoBTLE.networking.prettyprint.debug import debug_info_begin
from LegoBTLE.networking.prettyprint.debug import debug_info_end
from LegoBTLE.networking.prettyprint.debug import debug_info_footer
from LegoBTLE.networking.prettyprint.debug import debug_info_header


class AMotor(Device):
    """Abstract base class for Motors.
    
    """
    _on_stalled = None
    
    @property
    @abstractmethod
    def time_to_stalled(self) -> float:
        """Time To Stalled: The time after which `E_MOTOR_STALLED` may be set.
        
        The time that is allowed to pass without `port_value` changes.
        After that period `asyncio.Event` `E_MOTOR_STALLED` is set.
        
        Returns
        -------
        float
            The Time To Stalled in fractions of seconds.

        """
        raise NotImplementedError
    
    @time_to_stalled.setter
    def time_to_stalled(self, tts: float):
        raise NotImplementedError
    
    def port_value_EFF(self):
        return self.port_value.get_port_value_EFF(gearRatio=1.0)
    
    def current_angle(self, si: SI = SI.DEG) -> float:
        f"""Return the current angle of the motor in DEG or RAD.
        
        The current angle takes the `gear_ratio` into account.
        
        For the raw value the `port_value` should be used.
        A possible scenario looks like::
            import ...
            motor0 = SingleMotor(server=('127.0.0.1', 8888), port=PORT.A)
            current_angle = motor0.port_value
            print("Current accumulated motor angle stands at: current_angle)
        2963
        ::
            current_angle_DEG = motor0.port_value.m_port_value_DEG
            print("Current accumulated motor angle in DEG stands at: current_angle_DEG")
        1680.2356
        ::
            current_angle_DEG = motor0.current_angle(si=SI.DEG)
            print("Current accumulated motor angle in DEG stands at: #`current_angle_DEG`")
        1680.2356
        
        Keyword Args
        ------------
        si : SI, default SI.DEG
            Specifies the unit of the return value.

        Returns
        -------
        float
            The current value of the motor in the specified unit (currently DEG or RAD) scaled by the gearRatio.
        """
        if si == SI.DEG:
            if self.port_value is not None:
                return self.port_value.m_port_value_DEG / self.gearRatio
        elif si == SI.RAD:
            if self.port_value is not None:
                return self.port_value.m_port_value_RAD / self.gearRatio
    
    def last_angle(self, si: SI = SI.DEG) -> float:
        f"""The last recorded motor angle.
        
        Keyword Args
        ------------
        si : SI
            Specifies the unit of the return value.

        Returns
        -------
        float
            The last recorded angle in units si scaled by the gearRatio.
        """
        if si == SI.DEG:
            if self.last_value is not None:
                return self.last_value.m_port_value_DEG / self.gearRatio
        elif si == SI.RAD:
            if self.last_value is not None:
                return self.last_value.m_port_value_RAD / self.gearRatio

    @property
    @abstractmethod
    def synced(self) -> bool:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def stall_bias(self) -> float:
        raise NotImplementedError

    @stall_bias.setter
    @abstractmethod
    def stall_bias(self, stall_bias: float):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_STALLING_IS_WATCHED(self) -> Event:
        """`asyncio.Event` indicating if motor stalling is currently watched.
        
        If this event is set, a task is currently watching if this motor is in a stall condition.
        This Event could be seen as a sentinel to prevent superfluous task creations, i.e., each motor command first
        issues an `asyncio.create_task` call to switch on stall detection. If this `Event` has already been set, task
        creation is skipped.
        
        Returns
        -------
        Event
            The respective event in this motor object.
            
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_MOTOR_STALLED(self) -> Event:
        """Event indicating a stalling condition.
        
        Returns
        ---
        Event
            Indicates if motor Stalled. This event can be waited for.
        
        """
        raise NotImplementedError

    async def _on_stalled_do(self, action: Optional[Awaitable]):
        while not self.E_MOTOR_STALLED.is_set():
            await asyncio.sleep(0.001)
        debug_info(f"{self.name}:{self.port[0]} >>> STALLED STALLED STALLED <<<", debug=self.debug)
        debug_info(f"{self.name}:{self.port[0]} CURRENT ANGLE: {self.port_value}", debug=self.debug)
        t = await action
        return True
        
    @property
    @abstractmethod
    def _last_stall_status(self) -> bool:
        raise NotImplementedError

    @_last_stall_status.setter
    @abstractmethod
    def _last_stall_status(self, stall_status: bool) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def max_steering_angle(self) -> float:
        raise NotImplementedError

    @max_steering_angle.setter
    @abstractmethod
    def max_steering_angle(self, max_steering_angle: float):
        raise NotImplementedError
    
    async def _watch_stalling(self, tts: float = None):
        if tts is None:
            tts = self.time_to_stalled
        debug_info("IN WATCHSTALLED", debug=self.debug)
        self.E_MOTOR_STALLED.clear()
        self.E_STALLING_IS_WATCHED.set()
        while True:
            if (not self.E_CMD_STARTED.is_set()) or (self.port_value is None):
                await asyncio.sleep(0.01)
                continue
            else:
                t0 = monotonic()
                m0: float = self.port_value.m_port_value_DEG
                await asyncio.sleep(tts)
                delta = abs(self.port_value.m_port_value_DEG - m0)
                delta_t = monotonic()-t0
                print(f"STALLCHECKING: {delta} / {delta_t}")
                if delta < self.stall_bias:
                    self.E_MOTOR_STALLED.set()
                    try:
                        await self._on_stalled()
                    except TypeError:
                        pass
                else: # (delta >= self.stall_bias)):
                    self.E_MOTOR_STALLED.clear()
    
    @property
    @abstractmethod
    def wheel_diameter(self) -> float:
        raise NotImplementedError
    
    @wheel_diameter.setter
    @abstractmethod
    def wheel_diameter(self, diameter: float = 100.0):
        """
        
        Keyword Args:
            diameter (float): The wheel wheel_diameter in mm.

        Returns:
            nothing (None):
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def gearRatio(self) -> Union[Tuple[float, float], float]:
        """
        
        :return: The gear ratios.
        :rtype: tuple[float, float]
        """
        raise NotImplementedError
    
    @gearRatio.setter
    @abstractmethod
    def gearRatio(self, gearRatio: Union[Tuple[float, float], float]) -> None:
        """Sets the gear ratio(s) for the motor(s)
        
        :param Union[Tuple[float, float], float] gearRatio:
        :return:
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def current_profile(self) -> defaultdict:
        raise NotImplementedError
    
    @current_profile.setter
    @abstractmethod
    def current_profile(self, profile: defaultdict):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def acc_dec_profiles(self) -> defaultdict:
        raise NotImplementedError
    
    @acc_dec_profiles.setter
    @abstractmethod
    def acc_dec_profiles(self, profile: defaultdict):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def clockwise_direction(self) -> MOVEMENT:
        """The modifier to match the real clockwise turning direction.
        
        By defining the clockwise direction of this motor, the model can be aligned with the reality.
        Thus, by defining::
        
            FORWARD_MOTOR: SingleMotor = SingleMotor(...)
            FORWARD_MOTOR.clockwise_direction = MOVEMENT.COUNTERCLOCKWISE
        
        The user defined that the model's `FORWARD_MOTOR` motor's clockwise direction should in reality be a
        counter-clockwise movement.
         
        Returns
        -------
        MOVEMENT
           The real turning direction.
            
        """
        raise NotImplementedError

    @clockwise_direction.setter
    @abstractmethod
    def clockwise_direction(self, real_clockwise_direction):
        raise NotImplementedError
    
    async def SET_DEC_PROFILE(self,
                              ms_to_zero_speed: int,
                              profile_nr: int,
                              wait_cond: Union[Awaitable, Callable] = None,
                              wait_cond_timeout: float = None,
                              delay_before: float = None,
                              delay_after: float = None
                              ) -> bool:
        """
        Set the deceleration profile and profile number.
        
        The profile id then can be used in commands like :func:`GOTO_ABS_POS`, :func:`START_MOVE_DEGREES`.
        
        Keyword Args
        ----------

        ms_to_zero_speed  : int
            Time allowance to let the motor come to a halt.
        profile_nr : int
            A number to save the this deceleration profile under.
        wait_cond : Optional[Awaitable, Callable], optional
            A condition to wait for. The condition must be a callable that eventually results to true.
        wait_cond_timeout : float, optional
            An optional timeout after which the Condition is deemed true.
        delay_before : float, optional
            Add an optional delay before actual command execution (sending).
        delay_after : float, optional
            Add an optional delay after actual command execution (return from coroutine).
        
        Returns
        -------
        bool
            True if everything was OK, False otherwise.
            
        Raises
        ------
        TypeError, KeyError
            If None is erroneously given for `ms_to_zero_speed`, the algorithm tries to find the profile number in
            earlier defined profiles. If that fails the ``KeyError`` is raised, if something has been found but is of
            wrong type the ``TypeError`` is raised.
            
        See Also
        --------
        SET_ACC_PROFILE :
            The counter-part of this method, i.e., controlling the acceleration.
        
        """
        
        if self.debug:
            print(
                    f"{C.WARNING}{self.name}.SET_DEC_PROFILE AT THE GATES... {C.ENDC}"
                    f"{C.UNDERLINE}{C.OKBLUE}WAITING {C.ENDC}"
                    )
        
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            
            if self.debug:
                print(f"{C.WARNING}{self.name}.SET_DEC_PROFILE AT THE GATES... {C.OKBLUE}"
                      f"{C.OKBLUE}{C.UNDERLINE}PASSED {C.ENDC}"
                      )
            if self.debug:
                print(f"{C.WARNING}DELAY_BEFORE / {self.name} "
                      f"{C.WARNING}WAITING FOR {delay_before}... "
                      f"{C.BOLD}{C.OKBLUE}START {C.ENDC}"
                      )
            await sleep(delay_before)
            if self.debug:
                print(f"{C.WARNING}DELAY_BEFORE / {self.name} "
                      f"{C.WARNING}WAITING FOR {delay_before}... "
                      f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE {C.ENDC}"
                      )
            
            current_command = None
            if ms_to_zero_speed is None:
                try:
                    current_command = self.acc_dec_profiles[profile_nr]['DEC']
                except (TypeError, KeyError) as ke:
                    self.port_free.set()
                    self.port_free_condition.notify_all()
                    raise ke(f"SET_DEC_PROFILE {profile_nr} not found... {ke.args}")
            else:
                current_command = CMD_SET_ACC_DEACC_PROFILE(
                        profile_type=SUB_COMMAND.SET_DEACC_PROFILE,
                        port=self.port,
                        start_cond=MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                        completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                        time_to_full_zero_speed=ms_to_zero_speed,
                        profile_nr=profile_nr,
                        )
                try:
                    self.acc_dec_profiles[profile_nr]['DEC'] = current_command
                    self.current_profile['DEC'] = (profile_nr, current_command)
                except TypeError as te:
                    self.port_free.set()
                    self.port_free_condition.notify_all()
                    raise TypeError(f"SET_DEC_PROFILE {type(profile_nr)} wrong... {te.args}")
            
            if self.debug:
                print(f"{self.name}.SET_DEC_PROFILE SENDING {current_command.COMMAND.hex()}...")
            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
                
            s = await self._cmd_send(current_command)
            self.E_CMD_FINISHED.clear()
            
            if self.debug:
                print(f"{self.name}.SET_DEC_PROFILE SENDING COMPLETE...")
            if delay_after is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )

            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
            
            self.port_free.set()
            self.port_free_condition.notify_all()
        
        return s
    
    async def SET_ACC_PROFILE(self,
                              ms_to_full_speed: int,
                              profile_nr: int,
                              wait_cond: Union[Awaitable, Callable] = None,
                              wait_cond_timeout: float = None,
                              delay_before: float = None,
                              delay_after: float = None,
                              ) -> bool:
        r"""Define an Acceleration Profile and assign it an id.

        This method defines an Acceleration Profile and assigns a `profile_id`.
        It saves or updates the list of Acceleration Profiles and can be used in Motor Commands like
        :func:`GOTO_ABS_POS`, :func:`START_MOVE_DEGREES`

        Parameters
        ----------
        ms_to_full_speed : int
            Time after which the full speed is reached (100% relative, i.e. if the top speed is limited to 40% the 100%
            equal these 40%).
        delay_before : float, optional
            Milliseconds (ms) to wait before sending this command.
        delay_after : float, optional
            Milliseconds (ms) to wait, before continuing with the program execution.
        profile_nr : int
            The Profile ID-Nr..
        wait_cond : Union[Awaitable, Callable], optional.
            Instructs to wait until ``typing.Awaitable`` or ``typing.Callable`` is True.
        wait_cond_timeout : float, optional
            Sets an additional timeout after which waiting is quit.

        Returns
        --------
        bool :
            True if all is good, False otherwise.
            
        See Also
        --------
        SET_DEC_PROFILE : The counter-part of this method, i.e., controlling the acceleration.
        """
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            
            if self.debug:
                print(f"{C.WARNING}{self.name}.SET_ACC_PROFILE AT THE GATES... {C.ENDC}"
                      f"{C.UNDERLINE}{C.OKBLUE}{C.UNDERLINE}PASSED {C.ENDC}")
            if delay_before is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_BEFORE / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.OKBLUE}START {C.ENDC}"
                          )
                await sleep(delay_before)
                if self.debug:
                    print(f"{C.WARNING}DELAY_BEFORE / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE {C.ENDC}"
                          )
            
            current_command = None
            if ms_to_full_speed is None:
                try:
                    current_command = self.acc_dec_profiles[profile_nr]['ACC']
                except (TypeError, KeyError) as ke:
                    self.port_free_condition.notify_all()
                    self.port_free.set()
                    raise ke(f"SET_ACC_PROFILE {profile_nr} not found... {ke.args}")
            else:
                current_command = CMD_SET_ACC_DEACC_PROFILE(
                        profile_type=SUB_COMMAND.SET_ACC_PROFILE,
                        port=self.port,
                        start_cond=MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                        completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                        time_to_full_zero_speed=ms_to_full_speed,
                        profile_nr=profile_nr,
                        )
                try:
                    self.acc_dec_profiles[profile_nr]['ACC'] = current_command
                    self.current_profile['ACC'] = (profile_nr, current_command)
                except TypeError as te:
                    self.port_free.set()
                    self.port_free_condition.notify_all()
                    raise TypeError(f"Profile id [tp_id] is {profile_nr}... {te.args}")
            
            if self.debug:
                print(f"{self.name}.SET_ACC_PROFILE SENDING {current_command.COMMAND.hex()}...")
            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
                
            s = await self._cmd_send(current_command)
            self.E_CMD_FINISHED.clear()
            if self.debug:
                print(f"{self.name}.SET_ACC_PROFILE SENDING COMPLETE...")
            
            if delay_after is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )

            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
            
            self.port_free.set()
            self.port_free_condition.notify_all()
        return s

    async def START_MOVE_DISTANCE(self,
                                  distance: float,
                                  speed: int,
                                  abs_max_power: int = 30,
                                  use_profile: int = 0,
                                  use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
                                  use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
                                  on_completion: MOVEMENT = MOVEMENT.BREAK,
                                  on_stalled: Awaitable = None,
                                  time_to_stalled: float = None,
                                  wait_cond: Union[Awaitable, Callable] = None,
                                  wait_cond_timeout: float = None,
                                  delay_before: float = None,
                                  delay_after: float = None,
                                  ):
        """
        Convenience Method to drive the model a certain distance.
        
        The method uses :func: START_MOVE_DEGREES and calculates with a simple rule of three the degrees to turn in
        order to reach the distance.

        Keyword Args
        ----------

        
        distance : float
            Distance to drive in mm-fractions. :func: ``~np._sign(distance)`` determines the direction as does `speed`.
        speed : int
            The speed to reach the target. :func: ``~np._sign(speed)`` determines the direction `distance`.
        abs_max_power : int, default=30
            Maximum power level the System can reach.
        use_profile :
            Set the ACC/DEC-Profile number
        use_acc_profile : MOVEMENT
            
                * `MOVEMENT.USE_PROFILE` to use the acceleration profile set with use_profile.
            
                * `MOVEMENT.NOT_USE_PROFILE` to not use the profile set with use_profile.
        use_dec_profile : MOVEMENT
            
                * `MOVEMENT.USE_PROFILE` to use the deceleration profile set with `use_profile`.
            
                * `MOVEMENT.NOT_USE_PROFILE` to not use the profile set with `use_profile`.
        on_completion : MOVEMENT
            Determine how the motor should behave when finished movement.
        on_stalled : Awaitable
            Determine how the motor should behave stalled condition is detected. This parameter is an ``~asyncio.Awaitable``.
        time_to_stalled : float
            Determines the elapsed time after which the motor is deemed stalled.
        wait_cond : Callable
            Wait until a Condition is met. Must be a Callable evaluating to TRUE/FALSE.
        wait_cond_timeout : float
            Determines the elapsed time after which the WaitUntil-Condition is deemed met.
        delay_before : float
            Determines elapsed ms-fractions after which the motor starts to turn.
        delay_after :
            Determines elapsed ms-fractions after which the command may return.
        
        Note
        ----
            
        As mentioned above, ``distance`` and ``speed`` influence the direction of the movement:
        
        .. code:: python
    
            FWD: SingleMotor = SingleMotor(name='Forward Drive', port=PORT.A, gearRatio=2.67)
            FWD.START_MOVE_DISTANCE(distance=-100, speed=73, abs_abs_max_power=90,)
        
        The resulting movement is negative (FORWARD/REARWARD: depends on the motor setup).
        And
        
        ..code:: python
        
            FWD: SingleMotor = SingleMotor(name='Forward Drive', port=PORT.A, gearRatio=2.67)
            FWD.START_MOVE_DISTANCE(distance=-100,
                                    speed=-73,
                                    abs_abs_max_power=90,
                                    )
    
        The resulting movement is positive as both `distance` and `speed` are negative.
        
        Returns
        -------
        bool
            TRUE if all is good, FALSE otherwise.
        """
        degrees = np.floor((distance * 360) / (np.pi * self.wheel_diameter))
        s = await self.START_MOVE_DEGREES(degrees=degrees,
                                          speed=speed,
                                          abs_max_power=abs_max_power,
                                          on_completion=on_completion,
                                          on_stalled=on_stalled,
                                          use_profile=use_profile,
                                          use_acc_profile=use_acc_profile,
                                          use_dec_profile=use_dec_profile,
                                          time_to_stalled=time_to_stalled,
                                          wait_cond=wait_cond,
                                          wait_cond_timeout=wait_cond_timeout,
                                          delay_before=delay_before,
                                          delay_after=delay_after)
        
        self.total_distance += abs(distance)
        return s
    
    async def START_POWER_UNREGULATED(self,
                                      power: int,
                                      start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                                      on_stalled: Awaitable = None,
                                      time_to_stalled: float = None,
                                      wait_cond: Union[Awaitable, Callable] = None,
                                      wait_cond_timeout: float = None,
                                      delay_before: float = None,
                                      delay_after: float = None,
                                      ):
        r""" This command puts a certain amount of Power to the Motor.
        The motor, or virtual motor will not start turn but is merely pre-charged. This results in a more/less forceful
        turn when the command START_SPEED_UNREGULATED is sent.
        
        A detailed description can be found in the `LEGO Wireless Protocol 3.0.00`_ .
        
        Keyword Args
        ------------
        power : int
            The power to apply.
        start_cond : MOVEMENT
            Lalles
        time_to_stalled : float
            Set the timeout after which the motor, resp. this command is deemed stalled.
       
        Returns
        -------
        bool
            True if all is good, False otherwise.
            
        .. _`LEGO Wireless Protocol 3.0.00`: https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startpower-power
        """
        if not self.E_STALLING_IS_WATCHED.is_set():
            _wst = asyncio.create_task(self._watch_stalling(time_to_stalled))
            if on_stalled is not None:
                _ost = asyncio.create_task(self._on_stalled_do(on_stalled))
    
        wcd = None
        power *= self.clockwise_direction  # normalize speed
        
        debug_info_header(f"NAME: {self.name} / PORT: {self.port} # START_POWER_UNREGULATED", debug=self.debug)
        debug_info_begin(f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # WAITING AT THE GATES", debug=self.debug)
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            self._set_cmd_running(False)
        
            debug_info_end(f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # PASSED THE GATES", debug=self.debug)
        
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # delay_before {delay_before}s",
                        debug=self.debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # delay_before {delay_before}s",
                        debug=self.debug)
        
            current_command = CMD_START_PWR_DEV(
                    synced=False,
                    port=self.port,
                    power=power,
                    start_cond=start_cond,
                    completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS
                    )
        
            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # sending CMD", debug=self.debug)
            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
        
            s = await self._cmd_send(current_command)
        
            debug_info(f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # CMD: {current_command}", debug=self.debug)
            debug_info_end(
                    f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # sending CMD", debug=self.debug)
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
        
            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=self.debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port} / START_POWER_UNREGULATED # delay_after {delay_after}s",
                        debug=self.debug)

            self.port_free.set()
            self.port_free_condition.notify_all()
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port} # START_POWER_UNREGULATED", debug=self.debug)
        try:
            wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        return s
    
    async def START_SPEED_UNREGULATED(
            self,
            speed: int,
            abs_max_power: int = 30,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            on_stalled: Awaitable = None,
            time_to_stalled: float = None,
            wait_cond: Union[Awaitable, Callable] = None,
            wait_cond_timeout: float = None,
            delay_before: float = None,
            delay_after: float = None,
            ):
        r"""Start the motor.
        
        See [1]_ for a complete command description.
        
        Parameters
        ----------
        
        on_stalled :
        delay_after : float
        delay_before : float 
        time_to_stalled : float
        start_cond :
        completion_cond :
        speed : int
            The speed in percent.
        abs_max_power :
        use_profile :
        use_acc_profile : MOVEMENT
        use_dec_profile : MOVEMENT
        wait_cond : float
        wait_cond_timeout : float
        
        Notes
        -----
        If the port is a virtual port, both attached motors are started.
        Motors must actively be stopped with command STOP, a reset command or a command setting the position.
        
        References
        ----------
        .. [1] The Lego(c) documentation, https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeed-speed-maxpower-useprofile-0x07
        """
        _ost = None
        wcd = None
        if not self.E_STALLING_IS_WATCHED.is_set():
            _wst = asyncio.create_task(self._watch_stalling(time_to_stalled))
        if on_stalled is not None:
            _ost = asyncio.create_task(self._on_stalled_do(on_stalled))
    
        speed *= self.clockwise_direction  # normalize speed
    
        debug_info_header(f"{self.name}:{self.port}.START_SPEED_UNREGULATED()", debug=self.debug)
        debug_info(f"{self.name}:{self.port}.START_SPEED_UNREGULATED(): AT THE GATES - WAITING", debug=self.debug)
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            self._set_cmd_running(False)
        
            debug_info(f"{self.name}:{self.port}.START_SPEED_UNREGULATED(): AT THE GATES - PASSED", debug=self.debug)
            if delay_before is not None:
                debug_info_begin(f"{self.name}:{self.port}.START_SPEED_UNREGULATED(): delay_before",
                                 debug=self.debug)
                await sleep(delay_before)
                debug_info_end(f"{self.name}:{self.port}.START_SPEED_UNREGULATED(): delay_before",
                               debug=self.debug)
        
            current_command = CMD_START_SPEED_DEV(
                    synced=False,
                    port=self.port,
                    start_cond=start_cond,
                    completion_cond=completion_cond,
                    speed=speed,
                    abs_max_power=abs_max_power,
                    use_profile=use_profile,
                    use_acc_profile=use_acc_profile,
                    use_dec_profile=use_dec_profile)
        
            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
        
            s = await self._cmd_send(current_command)
        
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
        
            if self.debug:
                print(f"{self.name}.START_SPEED SENDING COMPLETE...")
        
            if delay_after is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
        
            self.port_free.set()
            self.port_free_condition.notify_all()
        try:
            _ost.cancel()
            wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        return s
    
    async def GOTO_ABS_POS(
            self,
            position: int,
            speed: int = 30,
            abs_max_power: int = 30,
            time_to_stalled: float = None,
            on_stalled: Awaitable = None,
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            on_completion: MOVEMENT = MOVEMENT.BREAK,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            wait_cond: Union[Awaitable, Callable] = None,
            wait_cond_timeout: float = None,
            delay_before: float = None,
            delay_after: float = None,
            ):
        """Turn the Motor to an absolute position.

        .. seealso::
            https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-gotoabsoluteposition-abspos-speed-maxpower-endstate-useprofile-0x0d

        Returns
        ---
        bool
            True if OK, False otherwise.

        Keyword Args
        ----------

        
        position : int
            The position to go to.
        speed : int, default=30
            The speed.
        abs_max_power : int,default=30
            Maximum power level the motor is allowed to apply.
        time_to_stalled : float
            Time period (ms-fractions) after which the stagnant motor is deemed stalled
        on_stalled : Callable
            Set a callback in case motor is stalled, e.g. :func: port_value_set(port_value)
        on_completion : MOVEMENT
            Defines how the motor should behave after coming to a standstill (break, hold, coast).
        start_cond : MOVEMENT
            Defines how the command should be executed (immediately, buffer if necessary, etc.)
        completion_cond : MOVEMENT
            Defines how the command should end (report status etc.)
        use_profile :
        use_acc_profile :
        use_dec_profile :
        wait_cond : Callable
        wait_cond_timeout : float

        """
        _ost = None
        wcd = None
        if not self.E_STALLING_IS_WATCHED.is_set():
            _wst = asyncio.create_task(self._watch_stalling(time_to_stalled))
        if on_stalled is not None:
            _ost = asyncio.create_task(self._on_stalled_do(on_stalled))
                
        position *= self.clockwise_direction  # normalize left/right
        speed *= self.clockwise_direction  # normalize speed
        

        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            self._set_cmd_running(False)
            
            if self.debug:
                print(f"{C.WARNING}{self.name}.GOTO_ABS_POS AT THE GATES...{C.ENDC} "
                      f"{C.UNDERLINE}{C.UNDERLINE}{C.OKBLUE}PASSED {C.ENDC} ")
            
            if delay_before is not None:
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING}WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_before)
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING}WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
            
            current_command = CMD_GOTO_ABS_POS_DEV(
                    synced=False,
                    port=self.port,
                    start_cond=start_cond,
                    completion_cond=completion_cond,
                    speed=speed,
                    abs_pos=position,
                    gearRatio=self.gearRatio,
                    abs_max_power=abs_max_power,
                    on_completion=on_completion,
                    use_profile=use_profile,
                    use_acc_profile=use_acc_profile,
                    use_dec_profile=use_dec_profile,)

            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
            if self.debug:
                print(f"{self.name}.GOTO_ABS_POS SENDING {current_command.COMMAND.hex()}...")
                
            s = await self._cmd_send(current_command)
            
            if self.debug:
                print(f"{self.name}.GOTO_ABS_POS SENDING COMPLETE...")

            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND TO END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()

            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)

            if delay_after is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING}WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
            
            self.port_free.set()
            self.port_free_condition.notify_all()
        try:
            _ost.cancel()
            wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        return s
    
    async def STOP(self,
                   delay_before: float = None,
                   delay_after: float = None,
                   ):
        """Stop the motor immediately and cancel the currently running operation.
        
        Parameters
        ----------
        delay_before : float, default 0.0
            Delay command execution.
        delay_after : float, default 0.0
            Delay return from method.
            
        Returns
        -------
        bool
            Result holds the boolean status of the command-sending command.
            
        """
        wcd = None
        #if not self.E_STALLING_IS_WATCHED.is_set():
        #    _wst = asyncio.create_task(self._watch_stalling(self.time_to_stalled))
        
        if delay_before:
            await asyncio.sleep(delay_before)
        debug_info_header(f"{self.name}:{self.port}.STOP DIRECT CMD", debug=self.debug)
        debug_info_begin(f"{self.name}:{self.port}.STOP", debug=self.debug)
        # self._set_cmd_running(False)
        command = CMD_MODE_DATA_DIRECT(synced=self.synced,
                                       port=self.port,
                                       start_cond=MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                                       completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                                       preset_mode=WRITEDIRECT_MODE.SET_MOTOR_POWER,
                                       motor_position=0,
                                       )

        s = await self._cmd_send(command)
        await self.E_CMD_FINISHED.wait()
        debug_info(f"{self.name}:{self.port[0]}.STOP: CMD: {command}", debug=self.debug)
        if delay_after:
            await asyncio.sleep(delay_after)
        debug_info_end(f"{self.name}:{self.port[0]}.STOP CMD: {command}", debug=self.debug)
        debug_info_footer(f"{self.name}:{self.port[0]}.STOP DIRECT CMD", debug=self.debug)
        return s
    
    async def SET_POSITION(self,
                           pos: int = 0,
                           wait_cond: Union[Awaitable, Callable] = None,
                           wait_cond_timeout: float = None,
                           delay_before: float = None,
                           delay_after: float = None
                           ):
        wcd = None
        #if not self.E_STALLING_IS_WATCHED.is_set():
        #    _wst = asyncio.create_task(self._watch_stalling(self.time_to_stalled))
        
        if self.debug:
            print(f"{C.WARNING}{self.name}.SET_POSITION AT THE GATES...{C.ENDC} "
                  f"{C.OKBLUE}{C.UNDERLINE}WAITING{C.ENDC} ")
        
        async with self.port_free_condition:
            await self.port_free_condition.wait_for(lambda: self.port_free.is_set())
            self.port_free.clear()
            # self._set_cmd_running(False)
            
            if self.debug:
                print(f"{C.WARNING}{self.name}.SET_POSITION AT THE GATES...{C.ENDC} "
                      f"{C.UNDERLINE}{C.OKBLUE}{C.UNDERLINE}PASSED{C.ENDC} ")
    
            if delay_before is not None:
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_before)
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
    
            command = CMD_MODE_DATA_DIRECT(
                    port=self.port,
                    start_cond=MOVEMENT.ONSTART_BUFFER_IF_NEEDED,
                    completion_cond=MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                    preset_mode=WRITEDIRECT_MODE.SET_POSITION,
                    motor_position=pos,
                    )
    
            if self.debug:
                print(f"{self.name}:{self.port[0]}.SET_POSITION SENDING {command.COMMAND.hex()}...")

            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
            
            s = await self._cmd_send(command)
            
            debug_info_end(f"{self.name}:{self.port[0]}.SET_POSITION(): _cmd_send() ", debug=self.debug)
            
            t0 = monotonic()
            debug_info_begin(f"{self.name}:{self.port[0]}.SET_POSITION(): WAITING FOR COMMAND TO END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info_end(f"{self.name}:{self.port[0]}.SET_POSITION(): WAITED {monotonic() - t0}s FOR COMMAND TO END", debug=self.debug)
            
            if delay_after is not None:
                debug_info_begin(f"{self.name}:{self.port[0]}.SET_POSITION(): delay_after", debug=self.debug)
    
                await sleep(delay_after)
                
                debug_info_end(f"{self.name}:{self.port[0]}.SET_POSITION(): delay_after", debug=self.debug)
    
            self.port_free.set()
            self.port_free_condition.notify_all()
        # try:
        #     wcd.cancel()
        # except (CancelledError, AttributeError):
        #     pass
        return s
    
    async def START_MOVE_DEGREES(self,
                                 on_stalled: Optional[Awaitable],
                                 degrees: int,
                                 speed: int,
                                 abs_max_power: int = 30,
                                 time_to_stalled: float = None,
                                 start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
                                 completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
                                 on_completion: MOVEMENT = MOVEMENT.BREAK,
                                 use_profile: int = 0,
                                 use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
                                 use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
                                 wait_cond: Union[Awaitable, Callable] = None,
                                 wait_cond_timeout: float = None,
                                 delay_before: float = None,
                                 delay_after: float = None,
                                 ):
        r"""Move the Motor by a number of degrees.
        
        Turns the Motor by a defined number of `degrees`. A complete description can be found in [1]_.
        
        Parameters
        ----------
        degrees : int
            The target angle to reach (default in DEG).
        speed : int
            The desired speed in % max.
        abs_max_power : int, default 30
            The absolute maximum power the motor is allowed to use to reach/keep the desired `speed`.
        on_stalled : Awaitable, optional
            Defines what the motor should do in case it reached a stalled condition
        time_to_stalled  : float, optional
            Defines the time of no motor angle changes after which the motor is deemed stalled.
        
        Other Parameters
        ----------------
        delay_after : float
            Time delay before executing other commands.
        delay_before : float
            Time delay, before executing THIS command.
        on_completion : {MOVEMENT.BREAK, MOVEMENT.HOLD, MOVEMENT.COAST}, MOVEMENT, optional
            Defines what the motor should do when having reached the target angle: BREAK, HOLD, COAST
        use_profile : int, default 0
            The DEC/ACC_PROFILE to use.
        use_acc_profile : {MOVEMENT.USE_ACC_PROFILE, MOVEMENT.NOT_USE_PROFILE}, MOVEMENT, default
            Use an Acceleration profile, or not.
        use_dec_profile : {MOVEMENT.USE_DEC_PROFILE, MOVEMENT.NOT_USE_PROFILE}, MOVEMENT, default
            Use an Deceleration profile, or not.
        wait_cond : Optional[Awaitable, Callable], optional
            If set any preceding command will not finish before this command evaluated to true.
        wait_cond_timeout : float, optional
            Timeout for waiting on `wait_cond`.
        start_cond : {MOVEMENT.ONSTART_EXEC_IMMEDIATELY, MOVEMENT.ONSTART_BUFFER_IF_NEEDED}, Movement, optional
            Defines the execution mode of this command (instantly: MOVEMENT.ONSTART_EXEC_IMMEDIATELY, or put in a
            one-command buffer, allowing to let the currently running command finish).
        completion_cond : {MOVEMENT.ONCOMPLETION_UPDATE_STATUS, MOVEMENT.ONCOMPLETION_NO_ACTION}, optional, default
            Defines what the motor should do after command has finished,i.e., report its status as finished
            (MOVEMENT.ONCOMPLETION_UPDATE_STATUS) or do nothing (MOVEMENT.ONCOMPLETION_NO_ACTION).
            
        Returns
        -------
        bool
            True if all is good, False otherwise.
            
        References
        ----------
        .. [1] The Lego(c) specification for this command, https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeedfordegrees-degrees-speed-maxpower-endstate-useprofile-0x0b
        """
        _ost = None
        wcd = None
        degrees *= self.clockwise_direction  # normalize left/right
        s = int(np.sign(degrees))
        speed *= s  # normalize speed
        _orig_tts = self.time_to_stalled
        self._on_stalled = on_stalled
        if time_to_stalled is not None:
            self.time_to_stalled = time_to_stalled
        
        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            # self._set_cmd_running(False)
            
            if self.debug:
                print(f"{self.name}.START_MOVE_DEGREES AT THE GATES...{C.ENDC} "
                      f"{C.UNDERLINE}{C.OKBLUE}{C.UNDERLINE}PASSED{C.ENDC} ")
            
            if delay_before is not None:
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_before)
                if self.debug:
                    print(f"DELAY_BEFORE / {C.WARNING}{self.name} "
                          f"{C.WARNING} WAITING FOR {delay_before}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
            
            current_command = CMD_START_MOVE_DEV_DEGREES(
                    synced=False,
                    port=self.port,
                    start_cond=start_cond,
                    completion_cond=completion_cond,
                    degrees=int(round(degrees * self.gearRatio)),
                    speed=speed,
                    abs_max_power=abs(abs_max_power),
                    on_completion=on_completion,
                    use_profile=use_profile,
                    use_acc_profile=use_acc_profile,
                    use_dec_profile=use_dec_profile)
            if self.debug:
                print(f"{self.name}.START_MOVE_DEGREES: SENDING {current_command.COMMAND.hex()}...")
            
            # _wait_until part
            try:
                wcd = await asyncio.create_task(self._on_wait_cond_do(wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
            except TypeError as te:
                pass
            
            s = await self._cmd_send(current_command)
            
            if self.debug:
                print(f"{self.name}.START_MOVE_DEGREES SENDING COMPLETE...")
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            while not self.E_CMD_FINISHED.is_set():
                await asyncio.sleep(0.01)
            # await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
            
            if delay_after is not None:
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING} WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.OKBLUE}START{C.ENDC}"
                          )
                await sleep(delay_after)
                if self.debug:
                    print(f"{C.WARNING}DELAY_AFTER / {self.name} "
                          f"{C.WARNING} WAITING FOR {delay_after}... "
                          f"{C.BOLD}{C.UNDERLINE}{C.OKBLUE}DONE{C.ENDC}"
                          )
            
            self.port_free.set()
            self.port_free_condition.notify_all()
        try:
            wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        self.time_to_stalled = _orig_tts
        return s
    
    async def START_SPEED_TIME(
            self,
            time: int,
            speed: int,
            power: int = 30,
            start_cond: MOVEMENT = MOVEMENT.ONSTART_EXEC_IMMEDIATELY,
            completion_cond: MOVEMENT = MOVEMENT.ONCOMPLETION_UPDATE_STATUS,
            on_completion: MOVEMENT = MOVEMENT.BREAK,
            on_stalled: Awaitable = None,
            use_profile: int = 0,
            use_acc_profile: MOVEMENT = MOVEMENT.USE_ACC_PROFILE,
            use_dec_profile: MOVEMENT = MOVEMENT.USE_DEC_PROFILE,
            time_to_stalled: float = None,
            wait_cond: Union[Callable, Awaitable] = None,
            wait_cond_timeout: float = None,
            delay_before: float = None,
            delay_after: float = None,
            ):
    
        r"""Turn on the motor for a given time.
        Turn on the motor for a given time after time has finished, stop [1]_.

        The motor can be set to turn for a given time holding the provided speed while not exceeding the provided
        power setting.

        Returns
        -------
        bool
            True if no errors in _cmd_send occurred, False otherwise.

        Parameters
        ----------
        wait_cond_timeout :
        delay_before :
        delay_after :
        use_dec_profile :
        use_acc_profile :
        wait_cond :
        on_completion :
        use_profile :
        on_stalled :
        
        References
        ----------
        .. [1] The Lego(c) documentation, https://lego.github.io/lego-ble-wireless-protocol-docs/index.html#output-sub-command-startspeedfortime-time-speed-maxpower-endstate-useprofile-0x09
        """
        _ost = None
        wcd = None
        
        if not self.E_STALLING_IS_WATCHED.is_set():
            _wst = asyncio.create_task(self._watch_stalling(time_to_stalled))
        if on_stalled is not None:
            _ost = asyncio.create_task(self._on_stalled_do(on_stalled))

        speed *= self.clockwise_direction  # normalize speed

        async with self.port_free_condition:
            await self.port_free.wait()
            self.port_free.clear()
            self._set_cmd_running(False)
            
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # PASSED THE GATES",
                           debug=self.debug)
            
            if delay_before is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # delay_before {delay_before}s",
                        debug=self.debug)
                await sleep(delay_before)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # delay_before {delay_before}s",
                        debug=self.debug)
            
            current_command = CMD_START_MOVE_DEV_TIME(
                    port=self.port,
                    start_cond=start_cond,
                    completion_cond=completion_cond,
                    time=time,
                    speed=speed,
                    power=power,
                    on_completion=on_completion,
                    use_profile=use_profile,
                    use_acc_profile=use_acc_profile,
                    use_dec_profile=use_dec_profile)

            debug_info_begin(
                    f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # sending CMD",
                    debug=self.debug)
            # _wait_until part
            if wait_cond:
                wcd = asyncio.create_task(self._on_wait_cond_do(wait_cond=wait_cond))
                await asyncio.wait({wcd}, timeout=wait_cond_timeout)
                
            s = await self._cmd_send(current_command)
            
            t0 = monotonic()
            debug_info(f"WAITING FOR COMMAND END: t0={t0}s", debug=self.debug)
            await self.E_CMD_FINISHED.wait()
            debug_info(f"WAITED {monotonic() - t0}s FOR COMMAND TO END...", debug=self.debug)
            
            debug_info(f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # CMD: {current_command}",
                       debug=self.debug)
            debug_info_end(f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # sending CMD",
                           debug=self.debug)
            
            if delay_after is not None:
                debug_info_begin(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # delay_after {delay_after}s",
                        debug=self.debug)
                await sleep(delay_after)
                debug_info_end(
                        f"NAME: {self.name} / PORT: {self.port[0]} / START_SPEED_TIME # delay_after {delay_after}s",
                        debug=self.debug)
   
            self.port_free.set()
            self.port_free_condition.notify_all()
            
        debug_info_footer(footer=f"NAME: {self.name} / PORT: {self.port[0]} # START_SPEED_TIME",
                          debug=self.debug)
        try:
            wcd.cancel()
        except (CancelledError, AttributeError):
            pass
        return s
    
    @property
    @abstractmethod
    def measure_start(self) -> Union[Tuple[Union[float, int], float], Tuple[Union[float, int], Union[float, int],
                                                                            Union[float, int], float]]:
        """
        CONVENIENCE METHOD -- This method acts like a stopwatch. It returns the current
        raw "position" of the motor. It can be used to mark the start of an experiment.
        
        :return: The current time and raw "position" of the motor. In case a synchronized motor is
            used the dictionary holds a tuple with values for all motors (virtual and 'real').
        :rtype: Union[Tuple[Union[float, int], float], Tuple[Union[float, int], Union[float, int], Union[float, int],
        float]]
        """
        raise NotImplementedError
    
    @property
    @abstractmethod
    def measure_end(self) -> Union[Tuple[Union[float, int], float], Tuple[Union[float, int], Union[float, int],
                                                                          Union[float, int], float]]:
        """
        CONVENIENCE METHOD -- This method acts like a stopwatch. It returns the current
        raw "position" of the motor. It can be used to mark the end of a measurement.

        :return: The current time and raw "position" of the motor. In case a synchronized motor is
            used the dictionary holds a tuple with values for all motors (virtual and 'real').
        :rtype: Union[Tuple[Union[float, int], float], Tuple[Union[float, int], Union[float, int], Union[float, int],
        float]]
        """
        raise NotImplementedError
    
    def distance_start_end(self, gearRatio=1.0) -> Tuple:
        r = tuple(map(lambda x, y: (x - y) / gearRatio, self.measure_end, self.measure_start))
        return r
    
    def avg_speed(self, gearRatio=1.0) -> Tuple:
        startend = self.distance_start_end(gearRatio)
        dt = abs(startend[len(startend) - 1])
        r = tuple(map(lambda x: (x / dt), startend))
        return r
    
    @property
    @abstractmethod
    def total_distance(self) -> float:
        raise NotImplementedError
    
    @total_distance.setter
    @abstractmethod
    def total_distance(self, total_distance: float):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def distance(self) -> float:
        """Returns the total distance travelled in mm since the last reset.
        """
        raise NotImplementedError
    
    @distance.setter
    @abstractmethod
    def distance(self, distance: float):
        raise NotImplementedError
