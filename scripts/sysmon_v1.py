# -*- coding: utf-8 -*-
"""
system monitoring tool
"""

__author__ = 'tarun mudgal'

import argparse
import builtins
import datetime
import json
import logging
import os
import signal
import sys
import time
import traceback
from collections import OrderedDict
from pathlib import Path

import psutil
from psutil._common import bytes2human

MIN_LOG_INTERVAL = 5
MAX_LOG_INTERVAL = 3600
VALID_SYS_PARAMS = ['memory', 'cpu', 'disk', 'network', 'all']


class ArgParseWrapper():
    @staticmethod
    def log_file(log_file):
        log_path = Path(log_file)
        if not os.path.exists(log_path.parent):
            raise argparse.ArgumentTypeError("invalid log file path '%s'" % log_file)
        return log_path

    @staticmethod
    def log_interval(interval):
        try:
            interval = int(interval)
        except Exception as fault:
            raise argparse.ArgumentTypeError("invalid log_interval '%s'. It should be "
                                             "an integer. Exception=%s" % (
                                                 interval, fault))
        if interval < MIN_LOG_INTERVAL or interval > MAX_LOG_INTERVAL:
            raise argparse.ArgumentTypeError("log_interval should be within the range of %s to "
                                             "%s (both inclusive)" % (MIN_LOG_INTERVAL,
                                                                      MAX_LOG_INTERVAL))
        return interval

    @staticmethod
    def capture(capture):
        capture = [c.strip() for c in capture.split(',')]
        invalid_sys_params = set(capture) - set(VALID_SYS_PARAMS)
        if invalid_sys_params:
            raise argparse.ArgumentTypeError("invalid system param '%s' passed for monitoring" %
                                             list(invalid_sys_params))
        if 'all' in capture:
            all_sys_params = VALID_SYS_PARAMS[:]
            all_sys_params.remove('all')
            capture = all_sys_params
        return capture

    @staticmethod
    def memory_threshold(threshold):
        try:
            threshold = int(threshold)
        except Exception as fault:
            raise argparse.ArgumentTypeError("invalid memory_threshold '%s'. It should be "
                                             "an integer. Exception=%s" % (
                                                 threshold, fault))
        if threshold < 1 or threshold > 99:
            raise argparse.ArgumentTypeError("memory_threshold should be within the range of 1 to "
                                             "99 (both inclusive)")
        return threshold

    @staticmethod
    def cpu_threshold(threshold):
        try:
            threshold = int(threshold)
        except Exception as fault:
            raise argparse.ArgumentTypeError("invalid cpu_threshold '%s'. It should be "
                                             "an integer. Exception=%s" % (
                                                 threshold, fault))
        if threshold < 1 or threshold > 99:
            raise argparse.ArgumentTypeError("cpu_threshold should be within the range of 1 to "
                                             "99 (both inclusive)")
        return threshold

    @staticmethod
    def disk_threshold(threshold):
        try:
            threshold = int(threshold)
        except Exception as fault:
            raise argparse.ArgumentTypeError("invalid disk_threshold '%s'. It should be "
                                             "an integer. Exception=%s" % (
                                                 threshold, fault))
        if threshold < 1 or threshold > 99:
            raise argparse.ArgumentTypeError("disk_threshold should be within the range of 1 to "
                                             "99 (both inclusive)")
        return threshold


class FileLogger(logging.Logger):
    def __init__(self, filename, name='file_logger'):
        logging.Logger.__init__(self, name)

        ''' logfile file'''
        fh = logging.FileHandler(filename)
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(message)s\n\n')
        fh.setFormatter(formatter)
        self.addHandler(fh)

    def traceback(self, fault):
        msg = "".join(traceback.format_exception(*sys.exc_info()))
        try:
            msg = "Error %s:%s. Traceback -" % (str(fault.__class__), str(fault)) + msg
        except Exception as error:
            msg = "Error %s:%s. Traceback -" % (repr(fault.__class__), repr(fault)) + msg
        self.error("%s", msg)

    def __del__(self):
        x = logging._handlers.copy()
        for i in x:
            self.removeHandler(i)
            i.flush()
            i.close()


class StreamLogger(logging.Logger):
    def __init__(self, stream=sys.stderr, name='stream_logger'):
        logging.Logger.__init__(self, name)
        sh = logging.StreamHandler(stream=stream)
        sh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s')
        sh.setFormatter(formatter)
        self.addHandler(sh)

    def __del__(self):
        x = logging._handlers.copy()
        for i in x:
            self.removeHandler(i)
            i.flush()
            i.close()


def signal_handler(sig, frame):
    print('User pressed Ctrl-C. Flushing remaining logs and exiting!')
    logging.shutdown()
    sys.exit(0)


def init_file_logger(log_file):
    log = FileLogger(log_file)
    builtins.flogobj = log
    print("file logger initialized. keep monitoring log file '%s' for resource utilization" %
          log_file)


def init_stream_logger(stream=sys.stderr):
    log = StreamLogger(stream=stream)
    builtins.slogobj = log
    print("stream logger initialized. all warnings will be displayed on '%s'" % stream)


def convert4humans(ntup):
    readings = OrderedDict()
    for name in ntup._fields:
        value = getattr(ntup, name)
        if name == 'percent':  # not in ['percent', 'fstype', 'mountpoint', 'device']:
            value = str(value) + '%'
        elif name in ['fstype', 'mountpoint', 'device']:
            pass
        else:
            value = bytes2human(value)
        readings[name] = value
    return readings


def ntup2dict(ntup):
    odict = OrderedDict()
    for name in ntup._fields:
        value = getattr(ntup, name)
        odict[name] = value
    return odict


def start_sys_monitoring(capture_params, log_interval, memory_threshold, cpu_threshold,
                         disk_threshold):
    while True:
        sys_stats = OrderedDict()

        sys_stats['current_time'] = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        if 'memory' in capture_params:
            sys_stats['memory'] = OrderedDict()
            virt_mem = psutil.virtual_memory()
            swap_mem = psutil.swap_memory()
            sys_stats['memory']['virtual_memory'] = convert4humans(virt_mem)
            sys_stats['memory']['swap_memory'] = convert4humans(swap_mem)

            if virt_mem.percent > memory_threshold:
                slogobj.warning("Alert: Current Virtual Memory (RAM) usage is %s%% which is "
                                "greater than the memory threshold %s%%" % (virt_mem.percent,
                                                                            memory_threshold))
            if swap_mem.percent > memory_threshold:
                slogobj.warning("Alert: Current SWAP Memory usage is %s%% which is greater than "
                                "the memory threshold %s%%" % (swap_mem.percent, memory_threshold))
        if 'cpu' in capture_params:
            sys_stats['cpu'] = OrderedDict()
            cpu_use_percent = psutil.cpu_percent(interval=1)
            sys_stats['cpu']['overall_cpu_usage'] = str(cpu_use_percent) + '%'
            if cpu_use_percent > cpu_threshold:
                slogobj.warning("Alert: Current CPU usage is %s%% which is "
                                "greater than the cpu threshold %s%%" % (cpu_use_percent,
                                                                         cpu_threshold))
            sys_stats['cpu']['cpu_count'] = psutil.cpu_count()
            per_cpu_percent = OrderedDict()
            for cp in enumerate(psutil.cpu_percent(percpu=True)):
                per_cpu_percent["CPU %s" % cp[0]] = str(cp[1]) + '%'
            sys_stats['cpu']['per_cpu_usage'] = per_cpu_percent

        if 'disk' in capture_params:
            sys_stats['disk'] = OrderedDict()
            overall_disk_usage = psutil.disk_usage('/')
            sys_stats['disk']['overall_disk_usage'] = convert4humans(overall_disk_usage)
            if overall_disk_usage.percent > disk_threshold:
                slogobj.warning("Alert: Current Disk usage is %s%% which is "
                                "greater than the disk threshold %s%%" % (
                                    overall_disk_usage.percent,
                                    disk_threshold))

            sys_stats['disk']['disk_io_counters'] = ntup2dict(psutil.disk_io_counters())
            disk_stats = OrderedDict()
            for part in psutil.disk_partitions(all=False):
                if os.name == 'nt':
                    if 'cdrom' in part.opts or part.fstype == '':
                        # skip cd-rom drives with no disk in it; they may raise
                        # ENOENT, pop-up a Windows GUI error for a non-ready
                        # partition or just hang.
                        continue
                disks_info = convert4humans(psutil.disk_usage(part.mountpoint))
                disks_info['fstype'] = part.fstype
                disks_info['mountpoint'] = part.mountpoint
                disk_stats[part.device] = disks_info
            sys_stats['disk']['per_partition_usage'] = disk_stats

        if 'network' in capture_params:
            sys_stats['network'] = OrderedDict()
            sys_stats['network']['overall_io_counters'] = ntup2dict(psutil.net_io_counters())

            per_nic_io_counters = OrderedDict()
            for nic, nic_val in psutil.net_io_counters(pernic=True).items():
                per_nic_io_counters[nic] = ntup2dict(nic_val)
            sys_stats['network']['per_nic_io_counters'] = per_nic_io_counters

        flogobj.info(json.dumps(sys_stats, indent=4))
        time.sleep(log_interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='''system monitor utility that accumulates resource utilization''')
    parser.add_argument('--log_file', type=ArgParseWrapper.log_file, default='sysmon.log',
                        help='''log file path''')
    parser.add_argument('--log_interval', type=ArgParseWrapper.log_interval, default=300,
                        help='''time interval in seconds in between  each log entry [allowed 
                        range: 5-3600]''')
    parser.add_argument('--capture', type=ArgParseWrapper.capture, default='all',
                        help='''comma separated list of sys params that needs to be monitored. 
                        Allowed values are: [memory, cpu, disk, network, all]''')
    parser.add_argument('--memory_threshold', type=ArgParseWrapper.memory_threshold, default=80,
                        help='''memory threshold percent after which Warning will be generated [
                        allowed range: 1-99]''')
    parser.add_argument('--cpu_threshold', type=ArgParseWrapper.cpu_threshold, default=80,
                        help='''cpu threshold percent after which Warning will be generated [
                        allowed range: 1-99]''')
    parser.add_argument('--disk_threshold', type=ArgParseWrapper.disk_threshold, default=80,
                        help='''disk threshold percent after which Warning will be generated [
                        allowed range: 1-99]''')
    args = parser.parse_args()

    print("args=%s" % args)
    # sys.exit(0)

    # set log_file and check if it exists
    # log_file = None
    # if not args.log_file:
    #     log_file = 'sysmon.log'
    # else:
    #     log_file = args.log_file
    #
    # log_path = Path(log_file)
    # if not os.path.exists(log_path.parent):
    #     raise Exception("log file path '%s' not found" % log_file)

    # logger initialization
    init_file_logger(args.log_file)
    init_stream_logger()

    # set log interval and verify range
    # log_interval = 300
    # if args.log_interval:
    #     if args.log_interval < MIN_LOG_INTERVAL or args.log_interval > MAX_LOG_INTERVAL:
    #         raise Exception("log_interval should be in between %s and %s (both inclusive)" % (
    #             MIN_LOG_INTERVAL, MAX_LOG_INTERVAL))
    #     log_interval = args.log_interval

    # assign a signal handler allowing script to perform cleanup before exiting
    signal.signal(signal.SIGINT, signal_handler)

    # start system monitoring
    start_sys_monitoring(args.capture, args.log_interval, args.memory_threshold,
                         args.cpu_threshold, args.disk_threshold)
