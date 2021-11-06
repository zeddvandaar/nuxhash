from configparser import Error
import json
import os
import time
import socket
import subprocess
import threading

import requests

from nuxhash.devices.nvidia import NvidiaDevice
from nuxhash.miners import miner
from nuxhash.utils import get_port

ALGORITHMS_info = dict([
    # ('beamv3', 'beamv3'),
    # ('octopus', 'octopus'),
    # ('ergo', 'ergo'),
    ('daggerhashimoto', 'ethash'),
    ('kawpow', 'kawpow'),
    # ('progpow_sero', 'progpow_sero'),
    # ('cuckoocycle', 'cuckoo_ae'),
])
ALGORITHMS = [alg_info for alg_info in ALGORITHMS_info]

class NBMinerAlgorithm(miner.Algorithm):

    def __init__(self, parent, nbminer_algorithm, **kwargs):
        algorithms = nbminer_algorithm.lower().split('_')
        miner.Algorithm.__init__(
            self, parent, name=nbminer_algorithm,
            algorithms=algorithms, **kwargs)
        self._nbminer_algorithm = nbminer_algorithm
        self._devices = []
        self._randport = get_port()
        self._address = (self.parent._address[0], self._randport)
        self._process = None
        self.ready = False

    def accepts(self, device):
        # TODO: Proper support table instead of blindly accepting team green.
        return isinstance(device, NvidiaDevice)

    @miner.needs_miner_running
    def set_devices(self, devices):
        assert all(self.accepts(device) for device in devices)
        self._transition(set(self._devices), set(devices))
        self._devices = devices

    @miner.Algorithm.benchmarking.setter
    def benchmarking(self, v):
        self._benchmarking = v
        devices = self._devices
        if len(devices) > 0:
            # NOTE: May break on dual mining algos, but satisfactory for now.
            self.set_devices([])
            self.set_devices(devices)

    def _transition(self, old, new):
        if old != new:
            self._stop_work()
            if len(new) != 0:    
                self._start_work(new)

    def _start_work(self, devices):
        device_nbminer_indexes = [str(self.parent.device_pcie_id_map[device.pci_bus]) for device in devices]

        miner_args = [self.parent.executable, 
                    '--api', self._address[0] + ':' + str(self._address[1]), 
                    '--algo', ALGORITHMS_info[self.name], 
                    '-o', self.parent.stratums[self.name], 
                    '-u', self.parent._subscription[1] + '.' + self.parent._subscription[2], 
                    '-d', ','.join(device_nbminer_indexes)
        ] + self.parent._extra_args
        
        # Start process.
        self._process = subprocess.Popen(
            args=miner_args,
            stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)

        # Send stdout to logger.
        log_thread = threading.Thread(
            target=miner.log_output, args=(self._process,))
        log_thread.start()

        time.sleep(3) 
        self.ready = True

    def _stop_work(self):
        if self._process != None:
            self._process.kill()
            self._process.wait()
            self._process = None
            self.ready = False

    @miner.needs_miner_running
    def current_speeds(self):

        if not self.ready:
            return [0] 

        try:
            ip, port = self._address
            responce = requests.get('http://' + ip + ':' + str(port) + '/api/v1/status')
            data = responce.json()
            return [device['hashrate_raw'] for device in data['miner']['devices']]

        except (socket.error, socket.timeout):
            return [0]

class NBMiner(miner.Miner):

    def __init__(self, config_dir):
        miner.Miner.__init__(self, config_dir)

        self.ready = False

        self.executable = config_dir/'nbminer'/'nbminer'
        self._address = ('127.0.0.1', 0)
        for algorithm in ALGORITHMS:
            runnable = NBMinerAlgorithm(self, algorithm, warmup_secs=miner.SHORT_WARMUP_SECS)
            self.algorithms.append(runnable)

    def load(self):

        process = subprocess.Popen(
            args=[self.executable, '--device-info-json'],
            stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)

        output = process.stdout.read()
        device_info = json.loads(output)
        self.device_pcie_id_map = dict([(device['pci_bus_id'], device['device_id']) for device in device_info['devices']])

        self.ready = True

    def unload(self):
        self.ready = False

    def is_running(self):
        return self.ready

    @miner.Miner.settings.setter
    def settings(self, v):
        miner.Miner.settings.setter(v)
        self._subscription = (v['nicehash']['region'],
            v['nicehash']['wallet'],
            v['nicehash']['workername'])
        if v['nbminer_miner']['listen'] == '':
            self._address = ('127.0.0.1', 0)
        else:
            ip, port = v['nbminer_miner']['listen'].split(':')
            self._address = (ip, port)
        self._extra_args = v['nbminer_miner']['args'].split()

