# -*- coding: utf-8 -*-

"""

LoggedFS-python
Filesystem monitoring with Fuse and Python
https://github.com/pleiszenburg/loggedfs-python

	src/loggedfs/_core/ipc.py: Fast IPC through a pipe

	Copyright (C) 2017-2019 Sebastian M. Ernst <ernst@pleiszenburg.de>

<LICENSE_BLOCK>
The contents of this file are subject to the Apache License
Version 2 ("License"). You may not use this file except in
compliance with the License. You may obtain a copy of the License at
https://www.apache.org/licenses/LICENSE-2.0
https://github.com/pleiszenburg/loggedfs-python/blob/master/LICENSE

Software distributed under the License is distributed on an "AS IS" basis,
WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for the
specific language governing rights and limitations under the License.
</LICENSE_BLOCK>

"""


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# IMPORT
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

import pickle
import queue
import struct
from subprocess import Popen, PIPE
import sys
import threading
import time


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CONST
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

PREFIX = b'\xBA\xDE\xAF\xFE'
LEN_DTYPE = 'Q' # uint64
WAIT_TIMEOUT = 0.1 # seconds


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CLASS: END OF TRANSMISSION
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class end_of_transmission:


	def __init__(self, id):

		self._id = id


	@property
	def id(self):
		return self._id


	def __repr__(self):

		return '<end of transmission on stream "{ID}">'.format(ID = self._id)


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CLASS: RECEIVER (SINGLE STREAM)
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class _receiver_class:


	def __init__(self, stream_id, in_stream, decoder_func, processing_func):

		self._id = stream_id
		self._s = in_stream
		self._f = processing_func
		self._q = queue.Queue()
		self._t = threading.Thread(target = decoder_func, args = (self._id, self._s, self._q))
		self._t.daemon = True
		self._t.start()


	def flush(self):

		while not self._q.empty():
			try:
				data = self._q.get_nowait()
			except queue.Empty:
				pass
			else:
				self._f(data)
				self._q.task_done()


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# ROUTINES: DECODER FUNCTIONS FOR RECEIVER
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

def _out_decoder(_id, _s, _q):

	prefix_len = len(PREFIX)
	while True:
		prefix = _s.read(prefix_len)
		if len(prefix) == 0: # end of pipe
			_q.put(end_of_transmission(_id))
			break
		data_len_encoded = _s.read(8)
		data_len = struct.unpack(LEN_DTYPE, data_len_encoded)[0]
		data_bin = _s.read(data_len)
		_q.put(pickle.loads(data_bin))


def _err_decoder(_id, _s, _q):

	while True:
		msg = _s.readline()
		if len(msg) == 0:
			_q.put(end_of_transmission(_id))
			break
		_q.put(msg.decode('utf-8'))


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# CLASS: MANAGING RECEIVERS (MULTIPLE STREAMS)
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class receiver_manager_class:


	def __init__(self, cmd_list, out_func, err_func, exit_func):

		self._exit_func = exit_func
		self._proc = Popen(cmd_list, stdout = PIPE, stderr = PIPE)
		self._proc_alive = True
		self._out_r = _receiver_class('out', self._proc.stdout, _out_decoder, out_func)
		self._err_r = _receiver_class('err', self._proc.stderr, _err_decoder, err_func)
		self._receive()


	def _receive(self):

		while self._proc_alive:
			time.sleep(WAIT_TIMEOUT)
			self._out_r.flush()
			self._err_r.flush()
			self._proc_alive = self._proc.poll() is None
		self._exit_func()


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# ROUTINES: SEND
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

def send(data):

	data_bin = pickle.dumps(data)
	data_len = struct.pack(LEN_DTYPE, len(data_bin))
	sys.stdout.buffer.write(PREFIX)
	sys.stdout.buffer.write(data_len)
	sys.stdout.buffer.write(data_bin)
	sys.stdout.flush()
