#!/usr/bin/env python
# Copyright (C) 2011-2015 Swift Navigation Inc.
# Contact: Fergus Noble <fergus@swift-nav.com>
#
# This source is subject to the license found in the file 'LICENSE' which must
# be be distributed together with this source. All other rights reserved.
#
# THIS CODE AND INFORMATION IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.

"""
The :mod:`piksi_tools.serial_link` module contains functions related to
setting up and running SBP message handling.
"""

import sys
import time

from sbp.logging                        import SBP_MSG_PRINT
from sbp.piksi                          import SBP_MSG_RESET
from sbp.system                         import SBP_MSG_HEARTBEAT
from sbp.client.drivers.pyserial_driver import PySerialDriver
from sbp.client.drivers.pyftdi_driver   import PyFTDIDriver
from sbp.client.loggers.json_logger     import JSONLogger
from sbp.client.loggers.null_logger     import NullLogger
from sbp.client.handler                 import Handler
from sbp.client.watchdog                import Watchdog

LOG_FILENAME = time.strftime("serial-link-%Y%m%d-%H%M%S.log.json")

SERIAL_PORT  = "/dev/ttyUSB0"
SERIAL_BAUD  = 1000000

def get_ports():
  """
  Get list of serial ports.
  """
  import serial.tools.list_ports
  return [p for p in serial.tools.list_ports.comports() if p[1][0:4] != "ttyS"]

def get_args():
  """
  Get and parse arguments.
  """
  import argparse
  parser = argparse.ArgumentParser(description="Swift Navigation SBP Client.")
  parser.add_argument("-p", "--port",
                      default=[SERIAL_PORT], nargs=1,
                      help="specify the serial port to use.")
  parser.add_argument("-b", "--baud",
                      default=[SERIAL_BAUD], nargs=1,
                      help="specify the baud rate to use.")
  parser.add_argument("-v", "--verbose",
                      action="store_true",
                      help="print extra debugging information.")
  parser.add_argument("-f", "--ftdi",
                      action="store_true",
                      help="use pylibftdi instead of pyserial.")
  parser.add_argument("-l", "--log",
                      action="store_true",
                      help="serialize SBP messages to autogenerated log file.")
  parser.add_argument("-t", "--timeout",
                      default=[None], nargs=1,
                      help="exit after TIMEOUT seconds have elapsed.")
  parser.add_argument("-w", "--watchdog",
                      default=[None], nargs=1,
                      help="alarm after WATCHDOG seconds have elapsed without heartbeat.")
  parser.add_argument("-r", "--reset",
                      action="store_true",
                      help="reset device after connection.")
  parser.add_argument("-o", "--log-filename",
                      default=[LOG_FILENAME], nargs=1,
                      help="file to log output to.")
  parser.add_argument("-a", "--append-log-filename",
                      default=[None], nargs=1,
                      help="file to append log output to.")
  parser.add_argument("-d", "--tags",
                      default=[None], nargs=1,
                      help="tags to decorate logs with.")
  return parser.parse_args()

def get_driver(use_ftdi=False, port=SERIAL_PORT, baud=SERIAL_BAUD):
  """
  Get a driver based on configuration options

  Parameters
  ----------
  use_ftdi : bool
    For serial driver, use the pyftdi driver, otherwise use the pyserial driver.
  port : string
    Serial port to read.
  baud : int
    Serial port baud rate to set.
  """
  if use_ftdi:
    return PyFTDIDriver(baud)
  return PySerialDriver(port, baud)

def get_logger(use_log=False, filename=LOG_FILENAME):
  """
  Get a logger based on configuration options.

  Parameters
  ----------
  use_log : bool
    Whether to log or not.
  filename : string
    File to log to.
  """
  if not use_log:
    return NullLogger()
  print "Logging at %s." % filename
  return JSONLogger(filename)

def get_append_logger(filename, tags):
  """
  Get a append logger based on configuration options.

  Parameters
  ----------
  filename : string
    File to log to.
  tags : string
    Tags to log out
  """
  if not filename:
    return NullLogger()
  print "Append logging at %s." % filename
  return JSONLogger(filename, "a", tags)

def printer(sbp_msg):
  """
  Default print callback

  Parameters
  ----------
  sbp_msg: SBP
    SBP Message to print out.
  """
  sys.stdout.write(sbp_msg.payload)

def watchdog_alarm():
  """
  Called when the watchdog timer alarms. Will raise a KeyboardInterrupt to the
  main thread and exit the process.
  """
  sys.stderr.write("ERROR: Watchdog expired!")
  import thread
  thread.interrupt_main()

def main():
  """
  Get configuration, get driver, get logger, and build handler and start it.
  """
  args = get_args()
  port = args.port[0]
  baud = args.baud[0]
  timeout = args.timeout[0]
  log_filename = args.log_filename[0]
  append_log_filename = args.append_log_filename[0]
  watchdog = args.watchdog[0]
  tags = args.tags[0]
  # Driver with context
  with get_driver(args.ftdi, port, baud) as driver:
    # Handler with context
    with Handler(driver.read, driver.write, args.verbose) as link:
      # Logger with context
      with get_logger(args.log, log_filename) as logger:
        with get_append_logger(append_log_filename, tags) as append_logger:
          link.add_callback(printer, SBP_MSG_PRINT)
          link.add_callback(logger)
          link.add_callback(append_logger)
          # Reset device
          if args.reset:
            link.send(SBP_MSG_RESET, "")
          # Setup watchdog
          if watchdog:
            link.add_callback(Watchdog(float(watchdog), watchdog_alarm), SBP_MSG_HEARTBEAT)
          try:
            if timeout is not None:
              expire = time.time() + float(args.timeout[0])

            while True:
              if timeout is None or time.time() < expire:
              # Wait forever until the user presses Ctrl-C
                time.sleep(1)
              else:
                print "Timer expired!"
                break
              if not link.is_alive():
                print "Thread died!"
                sys.exit(1)
          except KeyboardInterrupt:
            # Callbacks, such as the watchdog timer on SBP_HEARTBEAT call
            # thread.interrupt_main(), which throw a KeyboardInterrupt
            # exception. To get the proper error condition, return exit code
            # of 1. Note that the finally block does get caught since exit
            # itself throws a SystemExit exception.
            sys.exit(1)

if __name__ == "__main__":
  main()

