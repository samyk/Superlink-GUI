"""
GUI for the Superconductor Technologies SuperLink Cryocooler serial interface (extracted from STI SuperLink RX RF Filter)

provides:
- Cold finger temperature
- Rejection temperature
- Power drawn
- Switching between Auto + Manual shutdown modes
"""

debug = 0

# Offset and gain values for temperature variables
Tcold_offset = 5.814
Tcold_gain = -0.01559

Trej_offset = 12.537
Trej_gain = -0.0344

Power_Scaling = 0.0075

# The various states of the superlink
SuperlinkModeOptions = ["Auto", "Manual"]
SuperlinkStateOptions = ["Initial", "Cooldown", "Regulate", "Bypass", "Shutdown"]

from tkinter import *
import glob
import time
import serial
import signal
import sys
import serial.tools.list_ports

def p(msg):
	if debug:
		print(msg)

def truncate(f, n): # Thanks internet stranger! http://stackoverflow.com/questions/783897/truncating-floats-in-python
	'''Truncates/pads a float f to n decimal places without rounding'''
	s = '{}'.format(f)
	if 'e' in s or 'E' in s:
		return '{0:.{1}f}'.format(f, n)
	i, p, d = s.partition('.')
	return '.'.join([i, (d+'0'*n)[:n]])

# try to find the correct serial port
def findPort():
	for port in list(serial.tools.list_ports.comports()):
		p(vars(port))
		if port.hwid.find('SER=') != -1:
			return(port.device)
	return ""

def SerialQuery(query):
	p("TX> " + query)
	query_bytes = query.encode('ascii') # convert ascii input to bytes for serial
	ser.write(query_bytes)
	try:
		response = ser.readline()
		resp = response.decode('ascii').strip()
		p("rx  " + resp)
		if len(resp) > 0:
			p("")
	except serial.serialutil.SerialException:
		# if no response (ie if serial cable pulled out), return nothing. This doesn't acutally seem to work, need to fix.
		response = b''
	return response.decode('ascii').strip()


def convertTemp(raw_T, startpoint, endpoint, offset, gain):
	# need to convert the responses from bytes to ascii to integer
	# characters 22 to 25 are the cold side wide range temperature reading raw value. Need to convert it to Kelvin.

	try:
		temp = int(raw_T[startpoint:endpoint], 16)

		temp = (5.0*temp/32768 - offset)/gain

		return temp
	except ValueError:
		print("Error converting temperature!")
		return(0.00)

def convertPower(raw_P, startpoint, endpoint, scaling):
	# convert power response from bytes to ascii to integer
	try:
		pwr = int(raw_P[startpoint:endpoint], 16)

		pwr = ((5.0*pwr/32768)**2)/scaling

		return pwr
	except ValueError:
		print("Error converting power!")

		return(0.00)


# returns the position of the start of the nth char after the SearchFor string
def findAfter(char, SearchMsg, SearchFor, SpaceNum):
	StartPt = SearchMsg.find(SearchFor) + len(SearchFor)-1
	for x in range(1, SpaceNum+1):
		StartPt = SearchMsg.find(char, StartPt+1)

	return StartPt

# Initialize but don't start serial connection. Superlink uses 19200 baud connection. Timeout is arbitrary. Set the com port at run time.
ser = serial.Serial(port=None, baudrate=19200, timeout=3)

class App(Frame):

	def __init__(self, parent=None, **kw):
		Frame.__init__(self, parent, kw)

		# Use a grid

		self.columnconfigure(0, pad=20)
		self.columnconfigure(1, pad=20)
		self.columnconfigure(2, pad=20)
		self.columnconfigure(3, pad=20)
		self.columnconfigure(4, pad=20)

		self.rowconfigure(0, pad=3)
		self.rowconfigure(1, pad=3)
		self.rowconfigure(2, pad=3)
		self.rowconfigure(3, pad=3)
		self.rowconfigure(4, pad=3)
		self.rowconfigure(5, pad=3)

		self._start = 0.0
		self._elapsedtime = 0.0
		self._running = 0


		self.timestr = StringVar()
		self.TcoldWindow = StringVar()
		self.TrejWindow = StringVar()
		self.PowerWindow = StringVar()
		self.ComPortText = StringVar()
		self.SuperlinkModeWindow = StringVar()
		self.SuperlinkStateWindow = StringVar()


		self.makeWidgets()

	def makeWidgets(self):
		# Make all visible labels and buttons

		ButtonsRow = 5
		Button(self, text='Start serial comm', command=self.Start).grid(row=ButtonsRow, column = 0)
		Button(self, text='Stop serial comm', command=self.Stop).grid(row=ButtonsRow, column = 1)
		Button(self, text='Toggle mode', command=self.PowerToggle).grid(row = ButtonsRow, column = 2)
		Button(self, text='Quit', command=self.quit).grid(row=ButtonsRow, column = 3)


		ComEntry = Entry(self, textvariable=self.ComPortText)
		ComEntry.grid(row = 4, column = 1)
		ComEntry.insert(0, findPort())

		Label(self, text = "COM port").grid(row=4, column = 0)

		Label(self, text = "Time elapsed").grid(row=0, column = 2)
		l = Label(self, textvariable=self.timestr)
		l.grid(row=0, column=3)

		Label(self, text="T_cold (K)").grid(row=0, column=0)
		Tcold = Label(self, textvariable=self.TcoldWindow)
		Tcold.grid(row=0, column=1)

		Label(self, text="T_rej (K)").grid(row=1, column=0)
		Trej = Label(self, textvariable=self.TrejWindow)
		Trej.grid(row=1, column=1)

		Label(self, text="Power (W)").grid(row=2, column=0)
		Power = Label(self, textvariable=self.PowerWindow)
		Power.grid(row=2, column=1)

		Label(self, text="Status").grid(row=3, column=0)
		SuperlinkMode = Label(self, textvariable=self.SuperlinkModeWindow)
		SuperlinkMode.grid(row=3, column=1)
		SuperlinkState = Label(self, textvariable=self.SuperlinkStateWindow)
		SuperlinkState.grid(row=3, column = 2)


		self._setTime(self._elapsedtime)


	def _update(self):
		""" Update the label with elapsed time. """


		self._elapsedtime = time.time() - self._start
		self._setTime(self._elapsedtime)
		if ser.isOpen():
			# First, query for the temperatures
			query = '<TP OP="GT" LC="MS"/>' # Inquiry command for cold side and rejection temps.
			# Cold side temp is second bit (between spaces 1 and 2)
			# Rejection temp is third bit (between spaces 2 and 3)
			queryRet = SerialQuery(query)
			if len(queryRet)==0:
				ColdTemp = "Serial timed out"
				RejTemp = "Serial timed out"
			else:
				ColdTemp = convertTemp(queryRet, findAfter(" ", queryRet, query, 1) + 1, findAfter(" ", queryRet, query, 2), Tcold_offset, Tcold_gain)
				ColdTemp = round(ColdTemp, 1)
				RejTemp = convertTemp(queryRet, findAfter(" ", queryRet, query, 2) + 1, findAfter(" ", queryRet, query, 3), Trej_offset, Trej_gain)
				RejTemp =  round(RejTemp,1)

			# Text, query for the power
			query = '<PW OP="GT" LC="MS"/>' # inquiry command for cooler power
			queryRet = SerialQuery(query)

			if len(queryRet)==0:
				Power = "Serial timed out"
			else:
				# power is the first (zeroth) item in this query. The findAfter should still work fine.
				Power = convertPower(queryRet, findAfter(" ", queryRet, query, 0) + 1, findAfter(" ", queryRet, query, 1), Power_Scaling)
				Power = round(Power, 1)

			# last, query for the Superlink status and auto/manual mode

			query = '<TP OP="GT" LC="SM"/>'
			queryRet = SerialQuery(query)

			if len(queryRet)==0:
				SuperlinkMode= "Serial timed out"
				SuperlinkState= "Serial timed out"
			else:

				SuperlinkMode= int(queryRet[findAfter(" ", queryRet, query, 0)+1:findAfter(" ", queryRet, query, 0)+2])
				SuperlinkMode = SuperlinkModeOptions[SuperlinkMode]
				SuperlinkState= int(queryRet[findAfter(" ", queryRet, query, 1)+1:findAfter(" ", queryRet, query, 1)+2])
				SuperlinkState= SuperlinkStateOptions[SuperlinkState]

			# write everything to proper labels
			self.TcoldWindow.set(ColdTemp)
			self.TrejWindow.set(RejTemp)
			self.PowerWindow.set(Power)
			self.SuperlinkModeWindow.set(SuperlinkMode)
			self.SuperlinkStateWindow.set(SuperlinkState)

		else:
			# if serial is off, do nothing
			self.TcoldWindow.set("Serial connection off")


		self._timer = self.after(1000, self._update)

	def _setTime(self, elap):
		""" Set the time string to Minutes:Seconds:Hundreths """
		minutes = int(elap/60)
		seconds = int(elap - minutes*60.0)

		self.timestr.set('%02d:%02d' % (minutes, seconds))

	def Start(self):
		""" Start the stopwatch, ignore if running. """
		global ser
		if not self._running:
			if self.ComPortText.get() == "":
				self.TcoldWindow.set("Need to enter a COM port")
			else:
				try:
					# start serial connection on the proper port.
					ser = serial.Serial(port=self.ComPortText.get(), baudrate=19200, timeout=3)
				except serial.serialutil.SerialException:

					self.TcoldWindow.set("Serial error")

				self._start = time.time() - self._elapsedtime

				self._update()
				self._running = 1



	def Stop(self):
		""" Stop the stopwatch, ignore if stopped. """
		global ser
		if self._running:
			self.after_cancel(self._timer)
			self._elapsedtime = time.time() - self._start
			self._setTime(self._elapsedtime)
			self._running = 0
			# close serial port
			ser.close()

	def PowerToggle(self):
		# toggles the Cryocooler between auto and manual modes
		global ser
		if self._running and ser.isOpen():
			if self.SuperlinkModeWindow.get() == "Auto":
				query = '<TP OP="ST" LC="SM">1 4</TP>'
			else:
				query =  '<TP OP="ST" LC="SM">0 4</TP>'

			SerialQuery(query)

	def run(self):
		#self.root = Tk()
		#app = App(self.root)
		self.root = root
		self.root.title("Stupendous Superlink Serial Snooper")
		app.pack(side=TOP)
		self.root.mainloop()

root = Tk()
app = App(root)

def sigint_handler(sig, frame):
	#global app
	root.quit()
	root.update()

def main():
	signal.signal(signal.SIGINT, sigint_handler)
	app.run()

if __name__ == '__main__':
	main()

"""
  {
    "device": "/dev/cu.Maker3-3BBD",
    "name": "cu.Maker3-3BBD",
    "description": "n/a",
    "hwid": "n/a",
    "vid": "None",
    "pid": "None",
    "serial_number": "None",
    "location": "None",
    "manufacturer": "None",
    "product": "None",
    "interface": "None"
  },
  {
    "device": "/dev/cu.usbmodem24303",
    "name": "cu.usbmodem24303",
    "description": "EVOCam2",
    "hwid": "USB VID:PID=2F88:0001 LOCATION=0-2.4.3",
    "vid": 12168,
    "pid": 1,
    "serial_number": "None",
    "location": "0-2.4.3",
    "manufacturer": "VisionEngineering",
    "product": "EVOCam2",
    "interface": "None"
  },
  {
    "device": "/dev/cu.usbserial-FTH145P2",
    "name": "cu.usbserial-FTH145P2",
    "description": "TTL232R-3V3",
    "hwid": "USB VID:PID=0403:6001 SER=FTH145P2 LOCATION=1-1",
    "vid": 1027,
    "pid": 24577,
    "serial_number": "FTH145P2",
    "location": "1-1",
    "manufacturer": "FTDI",
    "product": "TTL232R-3V3",
    "interface": "None"
  }
"""
