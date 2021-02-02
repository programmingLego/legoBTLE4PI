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
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE                     *
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER                          *
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,                   *
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE                   *
#  SOFTWARE.                                                                                       *
# **************************************************************************************************

from abc import ABC, abstractmethod
from queue import Empty, Queue
from threading import Condition, Event, current_thread
from time import sleep

from colorama import init

from LegoBTLE.Constants import SIUnit
from LegoBTLE.Constants.MotorConstant import MotorConstant
from LegoBTLE.Constants.Port import Port
from LegoBTLE.Debug.messages import BBB, BBG, BBR, BBY, DBB, DBY, MSG
from LegoBTLE.Device.messaging import M_Code, M_Status, M_SubCommand, M_Type, Message


class Motor(ABC):
    """Abstract base class for all Motor Types."""
    
    @property
    @abstractmethod
    def debug(self) -> bool:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError
    
    @name.setter
    @abstractmethod
    def name(self, name: str):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def Q_rsltrcv_RCV(self) -> Queue:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def Q_cmdsnd_WAITING(self) -> Queue:
        raise NotImplementedError
    
    @property
    def Q_cmd_EXEC(self) -> Queue:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_VPORT_CTS(self) -> Event:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_PORT_CTS(self) -> Event:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def C_PORT_RTS(self) -> Condition:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def E_TERMINATE(self) -> Event:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def port(self) -> bytes:
        raise NotImplementedError
    
    @port.setter
    @abstractmethod
    def port(self, port: bytes):
        raise NotImplementedError

    @property
    @abstractmethod
    def virtualPort(self) -> bytes:
        raise NotImplementedError

    @virtualPort.setter
    @abstractmethod
    def virtualPort(self, port: bytes):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def gearRatio(self) -> float:
        raise NotImplementedError
    
    @gearRatio.setter
    @abstractmethod
    def gearRatio(self, gearRatio: float):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def previousAngle(self) -> float:
        raise NotImplementedError
    
    @previousAngle.setter
    @abstractmethod
    def previousAngle(self, value: float):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def currentAngle(self) -> float:
        raise NotImplementedError
    
    @currentAngle.setter
    @abstractmethod
    def currentAngle(self, value: float):
        raise NotImplementedError
    
    @property
    @abstractmethod
    def upm(self) -> float:
        raise NotImplementedError
    
    @property
    @abstractmethod
    def lastError(self) -> bytes:
        raise NotImplementedError
    
    @lastError.setter
    @abstractmethod
    def lastError(self, error):
        raise NotImplementedError
    
    def CmdSND(self):
        MSG((self.port.hex(), current_thread().name), msg="[{}]:[{}]-[SIG]: SENDER START COMPLETE...", doprint=True,
            style=BBG())
        
        while not self.E_TERMINATE.is_set():
            if self.E_TERMINATE.is_set():
                break
            
            with self.C_PORT_RTS:
                try:
                    command: Message = self.Q_cmdsnd_WAITING.get_nowait()  # (block=True, timeout=.1)
                    MSG((self.port.hex(),
                         current_thread().name,
                         command.data.hex(),
                         command.port.hex()), msg="[{}]:[{}]-[RTS]: RTS {} FOR PORT [{}]",
                        doprint=self.debug,
                        style=BBY())
                    self.C_PORT_RTS.wait_for(lambda: (self.E_PORT_CTS.is_set() or self.E_TERMINATE.is_set()))
                    MSG((self.port.hex(),
                         current_thread().name,
                         command.port.hex()), msg="[{}]:[{}]-[CTS]: CTS RECEIVED FOR PORT [{}]", doprint=True,
                        style=BBG())
                except Empty:
                    sleep(.004)
                    self.C_PORT_RTS.notify_all()
                    continue
                else:
                    self.E_PORT_CTS.clear()
                    MSG((self.port.hex(),
                         current_thread().name,
                         command.port.hex()), msg="[{}]:[{}]-[CTS]: LOCKING PORT [{}]", doprint=True, style=BBR())
                    MSG((self.port.hex(),
                         current_thread().name,
                         command.m_type.name,
                         command.port.hex()), msg="[{}]:[{}]-[SND]: SENDING COMMAND {} FOR PORT [{}]",
                        doprint=self.debug,
                        style=DBY())
                    self.Q_cmd_EXEC.put(command)
                    self.C_PORT_RTS.notify_all()
                    MSG((self.port.hex(),
                         current_thread().name,
                         command.m_type.name,
                         command.port.hex()), msg="[{}]:[{}]-[SND]: {} SENT FOR PORT [{}]", doprint=self.debug,
                        style=BBB())
                    continue
        MSG((self.port.hex(),
             current_thread().name), msg="[{}]:[{}]-[SIG]: COMMENCE CMD SENDER SHUT DOWN...", doprint=True,
            style=BBR())
        return
    
    def RsltRCV(self):
        MSG((self.port.hex(), current_thread().name), msg="[{}]:[{}]-[SIG]: RECEIVER START COMPLETE...", doprint=True,
            style=BBG())
        
        while not self.E_TERMINATE.is_set():
            if self.E_TERMINATE.is_set():
                break
            
            try:
                result: Message = self.Q_rsltrcv_RCV.get_nowait()
            except Empty:
                sleep(.0045)
                continue
            else:
                with self.C_PORT_RTS:
                    MSG((
                        self.port.hex(),
                        current_thread().name,
                        result.m_type.name,
                        result.cmd_return_value.hex() if result.cmd_return_value is not None else "NO_RET_VAL"),
                        msg="[{}]:[{}]-[RCV]: RECEIVED [{}] = [{}]...",
                        doprint=self.debug, style=BBB())
                    
                    if (result.m_type == M_Type.RCV_COMMAND_STATUS) and (result.cmd_status == M_Code.EXEC_FINISH):
                        self.E_PORT_CTS.set()
                        MSG((self.name,
                             result.port.hex(),
                             current_thread().name,
                             result.cmd_status.value.hex(),
                             result.port.hex()),
                            msg="\t\t[{}]:[{}]:[{}]-[CTS]: {}:FREEING PORT - CTS FOR PORT {} RECEIVED...",
                            doprint=self.debug, style=BBG())
                    elif result.m_type == M_Type.ERROR:  # error
                        self.E_PORT_CTS.set()
                        self.lastError = result.error_trigger_cmd
                        MSG((self.port.hex(),
                             current_thread().name,
                             self.port.hex()), msg="\t\t[{}]:[{}]-[CTS]: ERROR RESULT MESSAGE freeing port {}...",
                            doprint=self.debug, style=BBG())
                    elif result.m_type == M_Type.DEVICE_INIT:
                        if isinstance(self, SynchronizedMotor):
                            self.E_VPORT_CTS.set()
                            self.virtualPort = result.port
                            MSG((self.port.hex(),
                                current_thread().name,
                                self.port.hex()),
                                msg="\t\t[{}]:[{}]-[CTS]: VIRTUAL PORT SETUP MESSAGE freeing port {}...",
                                doprint=self.debug, style=BBG())
                        else:
                            MSG((self.port.hex(),
                                current_thread().name,
                                result.dev_type.name,
                                self.port.hex()),
                                msg="\t\t[{}]:[{}]-[CTS]: [{}] PORT SETUP MESSAGE freeing port {}...",
                                doprint=self.debug, style=BBG())
                        self.E_PORT_CTS.set()
                    elif result.m_type == M_Type.RCV_DATA:
                        self.previousAngle = self.currentAngle
                        self.currentAngle = int.from_bytes(result.cmd_return_value, byteorder='big', signed=True) / \
                            self.gearRatio
                    self.C_PORT_RTS.notify_all()
        MSG((self.port.hex(),
             current_thread().name), msg="[{}]:[{}]-[SIG]: COMMENCE RECEIVER SHUT DOWN...", doprint=True,
            style=BBR())
        return
    
    # Commands available
    def subscribeNotifications(self, deltaInterval=b'\x01', withFeedback=True):
        
        data: bytes = b'\x0a\x00' + \
                      M_Type.SND_NOTIFICATION_COMMAND.value + \
                      self.port + \
                      b'\x02' + \
                      deltaInterval + \
                      b'\x00\x00\x00' + \
                      bytes(M_Status.ENABLED.value)
        self.Q_cmdsnd_WAITING.put(Message(data=data, withFeedback=withFeedback))
        return

    def unsubscribeNotifications(self, deltaInterval=b'\x01', withFeedback=True):
        data: bytes = b'\x0a\x00' + \
                      M_Type.SND_NOTIFICATION_COMMAND.value + \
                      self.port + \
                      b'\x02' + \
                      deltaInterval + \
                      b'\x00\x00\x00' + \
                      bytes(M_Status.DISABLED.value)
        self.Q_cmdsnd_WAITING.put(Message(data=data, withFeedback=withFeedback))
        return
    
    def turnForT(self, milliseconds: int, direction=MotorConstant.FORWARD, power: int = 50,
                 finalAction=MotorConstant.BREAK, withFeedback=True):
        """This method can be used to calculate the data to turn a motor for a specific time period and send it to the
        command waiting multiprocessing.Queue of the Motor.

            :param milliseconds:
                The duration for which the motor type should turn.
            :param direction:
                Either the driving direction (MotorConstant.FORWARD or MotorConstant.BACKWARD) or the steering direction
                (MotorConstant.LEFT or MotorConstant.RIGHT).
            :param power:
                A value between 0 and 100 (%).
            :param finalAction:
                Determines how the motor should behave once the specified time has been reached,
                i.e.,
                    * MotorConstant.COAST = the motor does not stop immediately, but turns on its own until
                    coming to a standstill (through friction working against movement)

                    * MotorConstant.BREAK = the motor is stopped, but can be turned by external force

                    * MotorConstant.HOLD = Motor is held in the end position, even if external forces try to
                    rotate the engine
            :param withFeedback:
                TRUE: Feedback is required.
                FALSE: No feedback required.
            :returns:
                None
        """
        
        power = int.from_bytes(direction.value, 'little', signed=True) * power if isinstance(direction, MotorConstant) \
            else int.from_bytes(direction, 'little', signed=True) * power
        power = int.to_bytes(power, 1, 'little', signed=True)
        
        finalAction = finalAction.value if isinstance(finalAction, MotorConstant) else finalAction
        
        try:
            assert self.port is not None
            
            port = self.port
            
            data: bytes = b'\x0c\x00' + \
                          M_Type.SND_MOTOR_COMMAND.value + \
                          port + \
                          b'\x11' + \
                          M_SubCommand.T_FOR_TIME.value + \
                          int.to_bytes(milliseconds, 2, byteorder='little', signed=False) + \
                          power + \
                          b'\x64' + \
                          finalAction + \
                          b'\x03'
        
        except AssertionError:
            print('[{}]-[ERR]: Motor has no port assigned... Exit...'.format(self))
            self.Q_cmdsnd_WAITING.put(Message())
        else:
            self.Q_cmdsnd_WAITING.put(Message(data=data, withFeedback=withFeedback))
        return
    
    def turnForDegrees(self, degrees: float, direction=MotorConstant.FORWARD, power: int = 50,
                       finalAction=MotorConstant.BREAK, withFeedback: bool = True):
        """This method is used to calculate the data to turn a motor for a specific value of degrees (°) and send
        this command to the command waiting multiprocessing.Queue of the Motor.

        :param degrees:
            The angle in ° by which the motor, i.e. its shaft, is to be rotated. An integer value, e.g. 10,
            12, 99 etc.
        :param direction:
            Either the driving direction (MotorConstant.FORWARD or MotorConstant.BACKWARD) or the steering direction (
            MotorConstant.LEFT or MotorConstant.RIGHT).
        :param power:
            A value between 0 an 100 (%)
        :param finalAction:
            Determines how the motor should behave once the specified time has been reached,
            i.e.,
                * MotorConstant.COAST = the motor does not stop immediately, but turns on its own until
                coming to a standstill (through friction working against movement)

                * MotorConstant.BREAK = the motor is stopped, but can be turned by external force

                * MotorConstant.HOLD = Motor is held in the end position, even if external forces try to
                rotate the engine
        :param withFeedback:
                TRUE: Feedback is required.
                FALSE: No feedback required.
        :returns:
                None
        """
        power = int.from_bytes(direction.value, 'little', signed=True) * power if isinstance(direction, MotorConstant) \
            else int.from_bytes(direction, 'little', signed=True) * power
        power = int.to_bytes(power, 1, 'little', signed=True)
        
        finalAction = finalAction.value if isinstance(finalAction, MotorConstant) else finalAction
        
        degrees = int.to_bytes(round(degrees * self.gearRatio), 4, byteorder='big',
                               signed=False)
        
        try:
            assert self.port is not None
            
            port = self.port
            
            data: bytes = b'\x0e\x00' + \
                          M_Type.SND_MOTOR_COMMAND.value + \
                          port + \
                          b'\x11' + \
                          M_SubCommand.T_FOR_DEGREES.value + \
                          degrees + \
                          power + \
                          b'\x64' + \
                          finalAction + \
                          b'\x03'
        
        except AssertionError:
            MSG((self,), msg="[{}]-[ERR]: Motor has no port assigned... Exit...", doprint=True, style=BBR())
            self.Q_cmdsnd_WAITING.put(Message())
        else:
            self.Q_cmdsnd_WAITING.put(Message(data=data, withFeedback=withFeedback))
        return
    
    def turnMotor(self, SI: SIUnit, unitValue: float = 0.0, direction=MotorConstant.FORWARD,
                  power: int = 50, finalAction=MotorConstant.BREAK, withFeedback: bool = True):
        """This method turns the Motor depending on the SI-Unit specified.

        :param SI:
            SI unit based on which the motor is to be turned (e.g. SIUnit.ANGLE).
        :param unitValue:
            By which value in the SI unit the motor is to be rotated.
        :param direction:
            Either the driving direction (MotorConstant.FORWARD or MotorConstant.BACKWARD) or the steering direction
            (MotorConstant.LEFT or MotorConstant.RIGHT).
        :param power: 
            A value between 0 and 100 (%).
        :param finalAction:
            Determines how the motor should behave after the rotations have ended,
            i.e.
            * MotorConstant.COAST = the motor does not stop immediately, but turns on its own until the
            Standstill;
            * MotorConstant.BREAK = the motor is stopped, but can be turned by external force
            will;
            * MotorConstant.HOLD = Motor is held in the end position, even if external forces try to
            to turn the engine.
        :param withFeedback:
                TRUE: Feedback is required.
                FALSE: No feedback required.
        :returns: 
            None
        """
        if SI == SI.ANGLE:
            self.turnForDegrees(unitValue, direction=direction, power=power, finalAction=finalAction,
                                withFeedback=withFeedback)
        elif SI == SI.TIME:
            self.turnForT(int(unitValue), direction=direction, power=power, finalAction=finalAction,
                          withFeedback=withFeedback)
    
    def reset(self, withFeedback: bool = True):
        """Reset the Motor to zero.

        :param withFeedback:
                TRUE: Feedback is required.
                FALSE: No feedback required.
        :returns:
            None
        """
        try:
            assert self.port is not None
            port = self.port
            
            data: bytes = b'\x0b\x00' + \
                          M_Type.SND_NOTIFICATION_COMMAND.value + \
                          port + \
                          b'\x11\x51\x02\x00\x00\x00\x00'
        
        except AssertionError:
            print('[{}]-[ERR]: Motor has no port assigned... Exit...'.format(self))
            self.Q_cmdsnd_WAITING.put(Message())
        else:
            self.currentAngle = 0.0
            self.previousAngle = 0.0
            self.Q_cmdsnd_WAITING.put(Message(data=data, withFeedback=withFeedback))


class SingleMotor(Motor):
    
    def __init__(self,
                 name: str = "SINGLE INTERNAL_MOTOR",
                 port=b'\x00',
                 gearRatio: float = 1.0,
                 synchronizedPart: bool = False,
                 cmdQ: Queue = None,
                 terminate: Event = None,
                 debug: bool = False):
        """The object that models a single motor at a certain port.

        :param synchronizedPart:
        :param name:
            A friendly name of the motor
        :param port:
            The port of the SingleMotor (LegoBTLE.Constants.Port can be utilised).
        :param gearRatio:
            The ratio of the number of teeth of the turning gear to the number of teeth of the turned gear.
        :param cmdQ:
            A common multiprocessing.Queue that queues all commands of all motors to be sent to the Hub for execution.
        :param terminate:
            The common terminate signal.
        :param debug:
            Setting
            * True: Debug messages on.
            * False: Debug messages off.
        """
        init()
        self._name: str = name
        
        self._port: bytes = port.value if isinstance(port, Port) else port
        
        self._gearRatio: float = gearRatio
        self._synchronizedPart: bool = synchronizedPart
        self._virtualPort: bytes = b'\xff'
        self._Q_cmd_EXEC: Queue = cmdQ
        self._Q_rsltrcv_RCV: Queue = Queue(maxsize=-1)
        self._Q_cmdsnd_WAITING: Queue = Queue(maxsize=-1)
        
        self._E_TERMINATE = terminate
        
        self._C_port_RTS: Condition = Condition()
        self._E_port_CTS: Event = Event()
        self._E_port_CTS.set()
        
        self._debug: bool = debug
        
        self._currentAngle: float = 0.00
        self._previousAngle: float = 0.00
        self._upm: float = 0.00
        
        self._lastError: bytes = b'\xff'
        return
    
    @property
    def E_TERMINATE(self) -> Event:
        return self._E_TERMINATE
    
    @property
    def debug(self) -> bool:
        return self._debug
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def port(self) -> bytes:
        return self._port

    @property
    def virtualPort(self) -> bytes:
        return self._virtualPort

    @virtualPort.setter
    def virtualPort(self, port: bytes):
        self._virtualPort = port
        return
    
    @property
    def Q_cmdsnd_WAITING(self) -> Queue:
        return self._Q_cmdsnd_WAITING
    
    @property
    def Q_rsltrcv_RCV(self) -> Queue:
        return self._Q_rsltrcv_RCV
    
    @property
    def Q_cmd_EXEC(self) -> Queue:
        return self._Q_cmd_EXEC
    
    @property
    def E_PORT_CTS(self) -> Event:
        return self._E_port_CTS
    
    @property
    def E_VPORT_CTS(self) -> Event:
        return Event()
    
    @property
    def C_PORT_RTS(self) -> Condition:
        return self._C_port_RTS
    
    @property
    def gearRatio(self) -> float:
        return self._gearRatio
    
    @property
    def previousAngle(self) -> float:
        return self._previousAngle
    
    @previousAngle.setter
    def previousAngle(self, value: float):
        self._previousAngle = value
        return
    
    @property
    def currentAngle(self) -> float:
        return self._currentAngle
    
    @currentAngle.setter
    def currentAngle(self, value: float):
        self._currentAngle = value
        return
    
    @property
    def upm(self) -> float:
        return self._upm
    
    @property
    def lastError(self) -> bytes:
        return self._lastError
    
    @lastError.setter
    def lastError(self, error):
        self._lastError = error.value if isinstance(error, M_Code) else error
        return

    @property
    def synchronized(self) -> bool:
        return self._synchronizedPart

    @synchronized.setter
    def synchronized(self, synchronized: bool=False):
        self._synchronizedPart = synchronized
        return

    def setToMid(self) -> float:
        """This method positions a motor in mid position between two (mechanical) boundaries.

        :rtype:
            float
        :return:
            The maximum degree to which the motor can turn in either direction.
        """
        self.turnForDegrees(degrees=180, direction=MotorConstant.LEFT, power=20, finalAction=MotorConstant.BREAK,
                            withFeedback=True)
        self.reset(withFeedback=True)
        self.turnForDegrees(degrees=180, direction=MotorConstant.RIGHT, power=20, finalAction=MotorConstant.BREAK,
                            withFeedback=True)
        
        maxSide2Side = abs(self.currentAngle)
        self.turnForDegrees(degrees=maxSide2Side / 2, direction=MotorConstant.LEFT, power=80,
                            finalAction=MotorConstant.BREAK,
                            withFeedback=True)
        self.reset(withFeedback=True)
        
        return maxSide2Side / 2


class SynchronizedMotor(Motor):
    """Combination of two separate Motors that are operated in a synchronized manner.
    """
    
    def __init__(self,
                 name: str="Single Virtual Motor from two synchronized Motors",
                 port: bytes=b'\xff',
                 firstMotor: SingleMotor = None,
                 secondMotor: SingleMotor = None,
                 gearRatio: float = 1.0,
                 cmdQ: Queue = None,
                 terminate: Event = None,
                 debug: bool = False):
        """

        :param name:
        :param port:
        :param firstMotor:
        :param secondMotor:
        :param gearRatio:
        :param execQ:
        :param terminate:
        :param debug:
        """
        init()
        self._name: str = name
        self._port: bytes = port.value if isinstance(port, Port) else port
        self._firstMotor: SingleMotor = firstMotor
        self._E_FM_PORT_CTS: Event = self._firstMotor.E_PORT_CTS
        self._secondMotor: SingleMotor = secondMotor
        self._E_SM_PORT_CTS: Event = self._secondMotor.E_PORT_CTS
        self._gearRatio: float = gearRatio
        
        self._Q_cmd_EXEC: Queue = cmdQ
        self._Q_rsltrcv_RCV: Queue = Queue(maxsize=-1)
        self._Q_cmdsnd_WAITING: Queue = Queue(maxsize=-1)
        
        self._E_TERMINATE: Event = terminate
        
        self._E_VPORT_CTS: Event = Event()
        self._E_VPORT_CTS.set()
        self._C_VPORT_RTS: Condition = Condition()
        self._debug: bool = debug
        
        self._currentAngle: float = 0.00
        self._previousAngle: float = 0.00
        self._upm: float = 0.00
        
        self._lastError: bytes = b'\xff'
        return
    
    @property
    def E_TERMINATE(self) -> Event:
        return self._E_TERMINATE
    
    @property
    def Q_rsltrcv_RCV(self) -> Queue:
        return self._Q_rsltrcv_RCV
    
    @property
    def Q_cmdsnd_WAITING(self) -> Queue:
        return self._Q_cmdsnd_WAITING
    
    @property
    def Q_cmd_EXEC(self) -> Queue:
        return self._Q_cmd_EXEC
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def lastError(self) -> bytes:
        return self._lastError
    
    @lastError.setter
    def lastError(self, error: bytes):
        self._lastError = error
        return
    
    @property
    def C_PORT_RTS(self) -> Condition:
        return self._C_VPORT_RTS
    
    @property
    def E_PORT_CTS(self) -> Event:
        return self._E_VPORT_CTS
    
    @property
    def E_VPORT_CTS(self) -> Event:
        return self._E_VPORT_CTS
    
    @property
    def gearRatio(self) -> float:
        return self._gearRatio
    
    @property
    def port(self) -> bytes:
        return self._port
    
    @property
    def previousAngle(self) -> float:
        return self._previousAngle
    
    @property
    def currentAngle(self) -> float:
        return self._currentAngle
    
    @property
    def upm(self) -> float:
        return self._upm
    
    @property
    def debug(self) -> bool:
        return self._debug

    @property
    def virtualPort(self) -> bytes:
        return self._port

    @virtualPort.setter
    def virtualPort(self, port: bytes):
        self._port = port
        self._firstMotor.synchronized = True
        self._firstMotor.virtualPort = port
        self._secondMotor.synchronized = True
        self._secondMotor.virtualPort = port
        return
    
    @property
    def firstMotor(self) -> SingleMotor:
        return self._firstMotor
    
    @property
    def secondMotor(self) -> SingleMotor:
        return self._secondMotor
    
    def configureVirtualPort(self) -> None:
        """Issue the command to set a commonly used synchronized port (i.e. Virtual Port) for the synchronized Motor.

        :return:
            None
        """
        data: bytes = b'\x06\x00' + \
                      M_Type.SND_COMMAND_SETUP_SYNC_MOTOR.value + \
                      M_Status.ENABLED.value + \
                      self._firstMotor.port + \
                      self._secondMotor.port
        
        command: Message = Message(data=data, withFeedback=True)
        with self._C_VPORT_RTS:
            if self.debug:
                print("[{}]-[RTS]: COMMAND: SETUP SYNC PORT".format(self))
            
            self._C_VPORT_RTS.wait_for(
                lambda: (self._firstMotor.E_PORT_CTS.is_set() and self._secondMotor.E_PORT_CTS.is_set()) or (
                    self._E_TERMINATE.is_set()))
            if self._E_TERMINATE.is_set():
                self._C_VPORT_RTS.notify_all()
                return
            
            if self.debug:
                print("[{}]-[CTS]: COMMAND: SYNC PORT {}".format(self, command.data.hex()))
            
            self._E_VPORT_CTS.clear()
            self._firstMotor.E_PORT_CTS.clear()
            self._secondMotor.E_PORT_CTS.clear()
            
            if self.debug:
                print("[{}]-[SND] --> [HUB]: {}".format(self, command.data.hex()))
            
            self.Q_cmdsnd_WAITING.put(command)
            
            self._C_VPORT_RTS.notify_all()
            return