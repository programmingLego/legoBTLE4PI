#  MIT License
#
#  Copyright (c) 2021 Dietrich Christopeit
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
import queue
from threading import Thread, Event, Condition, current_thread
from abc import ABC, abstractmethod
from time import sleep

from LegoBTLE.Constants.Port import Port
from LegoBTLE.Constants.MotorConstant import MotorConstant
from LegoBTLE.Constants import SIUnit
from LegoBTLE.Device.Command import Command


class Motor(ABC):
    """Abstract base class for all Motor Types."""

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
    def rcvQ(self) -> queue.Queue:
        raise NotImplementedError

    @property
    @abstractmethod
    def execQ(self) -> queue.Queue:
        raise NotImplementedError

    @property
    @abstractmethod
    def portFree(self) -> Event:
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
    def port(self) -> int:
        raise NotImplementedError

    @port.setter
    @abstractmethod
    def port(self, port: int):
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
    def debug(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def setVirtualPort(self, port: int):
        raise NotImplementedError

    @property
    @abstractmethod
    def lastError(self) -> int:
        raise NotImplementedError

    @lastError.setter
    @abstractmethod
    def lastError(self, error: int):
        raise NotImplementedError

    @property
    def cvPortFree(self) -> Condition:
        raise NotImplementedError

    def receiver(self, terminate: Event):
        print("[{}]-[MSG]: Receiver started...".format(current_thread().getName()))

        while not terminate.is_set():
            if self.rcvQ.empty():
                sleep(0.5)
                continue
            result: Command = self.rcvQ.get()
            if self.debug:
                print(
                        "[{}]-[MSG]: RECEIVED DATA: {}...".format(current_thread().getName(), result.data))
            if (result.data[2]==0x82) and (result.data[4]==0x0a):
                if self.debug:
                    print(
                            "[{}]-[MSG]: freeing port {:02}...".format(current_thread().getName(), self.port))
                self.portFree.set()
                continue
            if result.error:  # error
                self.lastError = result.data
                self.portFree.set()
                continue

            if result.data[2]==0x45:
                self.previousAngle = self.currentAngle
                self.currentAngle = int(''.join('{:02}'.format(m) for m in result.data[4:7][::-1]),
                                        16) / self.gearRatio
                continue
            if result.data[2]==0x04:
                self.setVirtualPort(result.port)

            if self.debug:
                print(
                        "[{:02}]-[MSG]: received result: {:02}".format(result.data[3], result.data[len(result.data) - 1]))

        print("[{}]-[SIG]: RECEIVER SHUT DOWN COMPLETE...".format(current_thread().getName()))
        return

    # Commands available
    def turnForT(self, milliseconds: int, direction: int = MotorConstant.FORWARD, power: int = 50,
                 finalAction: int = MotorConstant.BREAK, withFeedback=True):
        """This method can be used to calculate the data to turn a motor for a specific time period and send it as
        command to the Hub.

            :param milliseconds:
                The duration for which the motor type should turn.
            :param direction:
                Either the driving direction (MotorConstant.FORWARD or MotorConstant.BACKWARD) or the steering direction (
                MotorConstant.LEFT or
                MotorConstant.RIGHT).
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
        power = direction.value * power

        try:
            assert self.port is not None

            port = self.port

            data: bytes = bytes.fromhex('0c0081{:02x}1109'.format(port) + milliseconds.to_bytes(2, byteorder='little',
                                                                                                signed=False).hex() \
                                        + \
                                        power.to_bytes(1, byteorder='little', signed=True).hex() + '64{:02x}03'.format(
                    finalAction.value))
        except AssertionError:
            print('[{}]-[ERR]: Motor has no port assigned... Exit...'.format(self))
            return None
        else:
            command: Command = Command(data=data, port=port, withFeedback=withFeedback)

            with self.cvPortFree:
                if self.debug:
                    print("[{}]-[CMD]: WAITING: Port free for COMMAND TURN FOR TIME".format(self))
                self.cvPortFree.wait_for(lambda: self.portFree.isSet())

                if self.debug:
                    print("[{}]-[SIG]: PASS: Port free for COMMAND TURN FOR TIME".format(self))
                self.portFree.clear()

                self.execQ.put(command)
                if self.debug:
                    print("[{}]-[SIG]: CMD SENT TO EXEC QUEUE for COMMAND TURN FOR TIME".format(self))

                self.cvPortFree.notifyAll()
            return

    def turnForDegrees(self, degrees: float, direction: int = MotorConstant.FORWARD, power: int = 50,
                       finalAction: int = MotorConstant.BREAK, withFeedback: bool = True):
        """This method is used to calculate the data to turn a motor for a specific value of degrees (°) and send
        this command to the Hub.


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

        power = direction * power
        degrees = round(degrees * self.gearRatio)

        try:
            assert self.port is not None

            port = self.port

            data: bytes = bytes.fromhex('0e0081{:02}110b'.format(port) + degrees.to_bytes(4,
                                                                                          byteorder='little',
                                                                                          signed=False).hex() \
                                        + power.to_bytes(1, byteorder='little',
                                                         signed=True).hex() + '64{:02}03'.format(
                    finalAction))
        except AssertionError:
            print('[{}]-[ERR]: Motor has no port assigned... Exit...'.format(self))
            return None
        else:
            command: Command = Command(data=data, port=port, withFeedback=withFeedback)
            with self.cvPortFree:
                if self.debug:
                    print("[{}]-[CMD]: WAITING: Port free for COMMAND TURN DEGREES".format(self))
                self.cvPortFree.wait_for(lambda: self.portFree.isSet())

                if self.debug:
                    print("[{}]-[SIG]: PASS: Port free for COMMAND TURN DEGREES".format(self))
                self.portFree.clear()

                self.execQ.put(command)
                if self.debug:
                    print("[{}]-[SIG]: CMD SENT TO EXEC QUEUE for COMMAND TURN FOR TIME".format(self))

                self.cvPortFree.notifyAll()
                self.cvPortFree.release()
            return

    def turnMotor(self, SI: SIUnit, unitValue: float = 0.0, direction: int = MotorConstant.FORWARD,
                  power: int = 50, finalAction: int = MotorConstant.BREAK,
                  withFeedback: bool = True):
        """Diese Methode dreht einen Motor, wobei der Aufrufer die Art durch die Angabe der Einheit spezifiziert.


        :param SI:
            SI-Einheit, basierend auf welcher der Motor gedreht werden soll (z.B. SIUnit.ANGLE).
        :param unitValue:
            Um welchen Wert in der Einheit SI soll gedreht werden.
        :param direction:
            Entweder die Fahrrichtung (MotorConstant.FORWARD oder MotorConstant.BACKWARD) oder die Lenkrichtung (
            MotorConstant.LEFT oder
            MotorConstant.RIGHT).
        :param power: 
            Ein Wert von 0 bis 100.
        :param finalAction:
            Bestimmt, wie sich der Motor, nachdem die Drehungen beendet wurden, verhalten soll,
            d.h. 
            * MotorConstant.COAST = der Motor hält nicht sofort an, sodern dreht sich aus eigener Kraft bis zum
            Stillstand; 
            * MotorConstant.BREAK = der Motor wird angehalten, kann jedoch durch Krafteinwirkung von aussen gedreht
            werden; 
            * MotorConstant.HOLD = Motor wird in der Endposition gehalten, auch wenn Kräfte von aussen versuchen,
            den Motor zu drehen.
        :param withFeedback:
                TRUE: Feedback is required.
                FALSE: No feedback required.
        :returns: 
            None
        """

        if SI==SI.ANGLE:
            self.turnForDegrees(unitValue, direction=direction, power=power, finalAction=finalAction,
                                withFeedback=withFeedback)
        elif SI==SI.TIME:
            self.turnForT(int(unitValue), direction=direction, power=power, finalAction=finalAction,
                          withFeedback=withFeedback)
        return

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

            data: bytes = bytes.fromhex('0b0081{:02}11510200000000'.format(port))
        except AssertionError:
            print('[{}]-[ERR]: Motor has no port assigned... Exit...'.format(self))
            return None
        else:
            self.currentAngle = 0.0
            self.previousAngle = 0.0
            command: Command = Command(data=data, port=port, withFeedback=withFeedback)
            with self.cvPortFree:
                if self.debug:
                    print("[{}]-[CMD]: WAITING: Port free for COMMAND RESET".format(self))
                self.cvPortFree.wait_for(lambda: self.portFree.isSet())

                if self.debug:
                    print("[{}]-[SIG]: PASS: Port free for COMMAND RESET".format(self))
                self.portFree.clear()

                self.execQ.put(command)
                if self.debug:
                    print("[{}]-[SIG]: CMD SENT TO EXEC QUEUE for COMMAND TURN FOR TIME".format(self))

                self.cvPortFree.notifyAll()
                self.cvPortFree.release()
            return


class SingleMotor(Thread, Motor):

    def __init__(self, name: str = "Single Motor", port: int = 0x00, gearRatio: float = 1.0, execQ: queue.Queue = None,
                 terminateOn: Event = None, debug: bool = False):
        """

        :param name:
        :param port:
        :param gearRatio:
        :param execQ:
        :param terminateOn:
        :param debug:
        """
        super().__init__()

        self._name: str = name
        if isinstance(port, Port):
            self._port: int = port.value
        else:
            self._port: int = port
        self._gearRatio: float = gearRatio

        self._execQ: queue.Queue = execQ
        self._rcvQ: queue.Queue = queue.Queue(maxsize=100)
        self._cmdQ: queue.Queue = queue.Queue()

        self._terminate: Event = terminateOn
        self._portFree: Event = Event()
        self._portFree.set()
        self._cvPortFree: Condition = Condition()
        self.setDaemon(True)
        self._debug: bool = debug

        self._currentAngle: float = 0.00
        self._previousAngle: float = 0.00
        self._upm: float = 0.00

        self._lastError: int = 0xff

    def run(self):
        if self._debug:
            print("[{}]-[MSG]: Started...".format(current_thread().getName()))
        receiver = Thread(target=self.receiver, args=(self._terminate,),
                          name="{} RECEIVER".format(self._name), daemon=True)
        receiver.start()

        self._terminate.wait()
        if self._debug:
            print("[{}]-[SIG]: SHUTTING DOWN...".format(current_thread().getName()))
        receiver.join()
        if self._debug:
            print("[{}]-[SIG]: SHUT DOWN COMPLETE...".format(current_thread().getName()))
        return

    @property
    def name(self) -> str:
        return self._name

    @property
    def rcvQ(self) -> queue.Queue:
        return self._rcvQ

    @property
    def execQ(self) -> queue.Queue:
        return self._execQ

    @property
    def portFree(self) -> Event:
        return self._portFree

    @property
    def gearRatio(self) -> float:
        return self._gearRatio

    @property
    def port(self) -> int:
        return self._port

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
    def debug(self) -> bool:
        return self._debug

    @property
    def lastError(self) -> int:
        return self._lastError

    @lastError.setter
    def lastError(self, error: int):
        self._lastError = error
        return

    def setVirtualPort(self, port: int):
        pass

    @property
    def cvPortFree(self) -> Condition:
        return self._cvPortFree

    def setToMid(self) -> Command:
        """This method positions a motor in mid position between two (mechanical) boundaries.

        :rtype:
            float
        :return:
            The maximum degree to which the motor can turn in either direction.
        """

        command: Command = None

        return command


class SynchronizedMotor(Thread, Motor):
    """Combination of two separate Motors that are operated in a synchronized manner.
    """

    def __init__(self, name: str, port: int = 0xff, firstMotor: SingleMotor = None, secondMotor: SingleMotor = None,
                 gearRatio: float = 1.0,
                 execQ: queue.Queue = None,
                 terminateOn: Event = None, debug: bool = False):
        """

        :param name:
        :param port:
        :param firstMotor:
        :param secondMotor:
        :param gearRatio:
        :param execQ:
        :param terminateOn:
        :param debug:
        """
        super().__init__()
        self._name: str = name
        self._port = port  # f"{ersterMotor.port:02}{zweiterMotor.port:02}"
        self._firstMotor: SingleMotor = firstMotor
        self._portFreeFM: Event = self._firstMotor.portFree
        self._secondMotor: SingleMotor = secondMotor
        self._portFreeSM: Event = self._secondMotor.portFree
        self._gearRatio: float = gearRatio

        self._execQ: queue.Queue = execQ
        self._rcvQ: queue.Queue = queue.Queue(maxsize=100)
        self._cmdQ: queue.Queue = queue.Queue()

        self._terminate: Event = terminateOn
        self._portFreeSync: Event = Event()
        self._portFreeSync.set()
        self._cvPortFreeSync: Condition = Condition()
        self.setDaemon(True)
        self._debug: bool = debug

        self._currentAngle: float = 0.00
        self._previousAngle: float = 0.00
        self._upm: float = 0.00

        self._lastError: int = 0xff

    @property
    def name(self) -> str:
        return self._name

    @property
    def rcvQ(self) -> queue.Queue:
        return self._rcvQ

    @property
    def execQ(self) -> queue.Queue:
        return self._execQ

    @property
    def portFree(self) -> Event:
        return self._portFreeSync

    @property
    def gearRatio(self) -> float:
        return self._gearRatio

    @property
    def port(self) -> int:
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

    def setVirtualPort(self, port: int):
        self._port = port

    @property
    def firstMotor(self) -> SingleMotor:
        return self._firstMotor

    @property
    def secondMotor(self) -> SingleMotor:
        return self._secondMotor

    @property
    def lastError(self) -> int:
        return self._lastError

    @lastError.setter
    def lastError(self, error: int):
        self._lastError = error
        return

    @property
    def cvPortFree(self) -> Condition:
        return self._cvPortFreeSync

    def setSynchronizedPort(self) -> None:
        """Issue the command to set a commonly used synchronized port (i.e. Virtual Port) for the synchronized Motor.

        :return:
            None
        """
        data: bytes = bytes.fromhex(
                '06006101' + '{:02}'.format(self._firstMotor.port) + '{:02}'.format(self._secondMotor.port))
        command: Command = Command(data=data, port=self._port, withFeedback=True)
        with self._cvPortFreeSync:
            if self.debug:
                print("[{}]-[CMD]: WAITING: Port free for COMMAND A".format(self))
            self._cvPortFreeSync.wait_for(lambda: self._firstMotor.portFree.isSet() & self._secondMotor.portFree.isSet())

            if self.debug:
                print("[{}]-[SIG]: PASS: Port free for COMMAND A".format(self))
            self._portFreeSync.clear()
            self._firstMotor.portFree.clear()
            self._secondMotor.portFree.clear()

            if self.debug:
                print("[{}]-[SIG]: CMD SENT TO EXEC QUEUE for COMMAND TURN FOR TIME".format(self))
            self.execQ.put(command)

            self._cvPortFreeSync.notifyAll()
            self._cvPortFreeSync.release()
        return
