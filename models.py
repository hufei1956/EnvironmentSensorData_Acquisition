from dataclasses import dataclass
import queue
import collections

class Sensor:
    def __init__(self, sensor_id):
        self._sensor_id = sensor_id
        self._data_queue = queue.Queue()
        self._attrs = {"WR_flag": None, "measurement_value": None, "AD_value": None, "Sensor_type": None}

    def id(self): 
        return self._sensor_id

    def add_data(self, data): 
        self._data_queue.put(data)

    def get_data(self): 
        return self._data_queue.get() if not self._data_queue.empty() else None

    def size(self): 
        return self._data_queue.qsize()

    def set_attr(self, k, v): 
        if k in self._attrs: 
            self._attrs[k] = v
        else: 
            raise KeyError(f"Invalid attribute: {k}")

    def get_attr(self, k): 
        return self._attrs.get(k)

class CircularBuffer:
    def __init__(self, size): 
        self.buffer = collections.deque(maxlen=size)

    def append(self, data): 
        # data can be an iterable of ints/bytes
        self.buffer.extend(data)

    def pop(self): 
        return self.buffer.popleft()

    def snapshot(self): 
        return list(self.buffer)

@dataclass
class DataRecord:
    index: int
    timestamp_str: str
    temperature: float
    humidity: float
    co2: int
    nh3: int
    ch4: int
    h2s: int
