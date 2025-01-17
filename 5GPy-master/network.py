import copy
from mimetypes import init
import sys
import abc
from scipy import rand
import simpy
import functools
import networkx as nx
import random
import time
from enum import Enum
import numpy
import utility as util
from scipy.stats import norm
import psutil


#This is the network module. It keeps all network elements, such as, processing nodes, RRHs, network nodes

#this dictionaire keeps all created network objects
elements = {}
generatedCPRI = 0

#this class represents a general frame
#aId is the fram id, payLoad is its data, src and dst is the source and destiny element, nextHop keeps the path from src to dst, procTime is the average time to process this frame
class Frame(object):
	def __init__(self, aId, payLoad, src, dst):
		self.aId = aId
		self.payLoad = payLoad
		self.src = src
		self.dst = dst
		self.nextHop = []
		self.inversePath = []#return path
		#self.localTransmissionTime = localTransmissionTime
		#self.procTime = procTime
		#self.switchTime = switchTime
		#self.transmissionTime = transmissionTime

#this class extends the basic frame to represent a basic eCPRI frame
#the ideia is that it carries payload from several users equipments and can carry one or more QoS classes of service
#users is a list of UEs being carried, 
#QoS are the classes of service carried on this fram and size is the bit rate of the frame
class ecpriFrame(Frame):
	def __init__(self, aId, payLoad, src, dst, users, QoS, size):
		super().__init__(aId, payLoad, src, dst)
		self.users = users
		self.QoS = QoS
		self.size = size

#this class represents a basic user equipment
#aId is the UE identification, posY and posX are the locations of the UE in a cartesian plane, applicationType is the kind of application accessed by the UE (e.g., video, messaging)
class UserEquipment(object):
	def __init__(self, env, aId, servingRRH, applicationType, localTransmissionTime):
		self.env = env
		self.aId = aId
		self.servingRRH = servingRRH
		#set the beginning position of each UE as the middle of its base station area
		self.posY = self.servingRRH.y2/2 
		self.posX = self.servingRRH.x2/2 
		#self.frameProcTime = frameProcTime
		self.localTransmissionTime = localTransmissionTime
		self.applicationType = applicationType
		self.ackFrames = simpy.Store(self.env)
		self.initiation = self.env.process(self.run())
		#self.action = self.env.process(self.sendFrame())
		self.latency = 0.0
		self.jitter = 0.0
		self.lastLatency = 0.0


	#TODO VOU MUDAR DE NOVO. OS UE NAO VAO GERAR QUADROS, APENAS ANDAR. O RRH AO GERAR O FRAME CPRI ASSUMIRÁ QUE RECEBEU UM QUADRO DE CADA UE
	#O CALCULO DO JITTER E DA TRANSMISSÃO SERÁ FEITO EM CIMA DA POSIÇÃO EM QUE CADA UE SE ENCONTRAR QUANDO O RRH GERAR O FRAME CPRI E QUANDO DEVOLVER (HIPOTETICAMENTE) O QUADRO A CADA UE
	#this method causes UEs to move
	def run(self):
		i = 0
		while True:
			#timeout for the UE to move
			yield self.env.timeout(0.5)
			self.randomWalk()
			#print("UE {} moved to position X = {} and Y = {}".format(hash(self), self.posX, self.posY))
			i += 1

	#TODO: Implement the limits of the UE to move (the combinations of the maximum values of axis y and x)
	#moves the UE
	def randomWalk(self):
		val = random.randint(1, 4)
		if val == 1:
			self.posX += 1
			self.posY = self.posY 
		if val == 2:
			self.posX -= 1
			self.posY = self.posY 
		elif val == 3:
			self.posX = self.posX 
			self.posY += 1
		else:
			self.posX = self.posX 
			self.posY -= 1

#this class represents a generic RRH
#it generates a bunch of UEs, receives/transmits baseband signals from/to them, generate eCPRI frames and send/receive them to/from processing
class RRH(object):
	def __init__(self, env, aId, distribution, cpriFrameGenerationTime, transmissionTime, localTransmissionTime, graph, cpriMode):
		self.env = env
		self.nextNode = None
		self.aType = "RRH"
		self.aId = "RRH"+":"+str(aId)
		self.frames = []
		self.users = []#list of active UEs served by this RRH
		self.nodes_connection = []#binary array that keeps the connection fron this RRH to fog nodes and cloud node(s)
		self.distribution = distribution#the distribution for the traffic generator distribution
		self.trafficGen = self.env.process(self.run())#initiate the built-in traffic generator
		#self.genFrame = self.env.process(self.takeFrameUE())
		self.uplinkTransmitCPRI = self.env.process(self.uplinkTransmitCPRI())#send eCPRI frames to a processing node
		self.downlinkTransmitUE = self.env.process(self.downlinkTransmitUE())#send frames to the UEs
		#thsi store receives frames back from the users
		self.received_users_frames = simpy.Store(self.env)
		#buffer to transmit to UEs
		self.currentLoad = 0
		#this store receives frames back from the processing nodes
		#self.received_eCPRI_frames = simpy.Store(self.env)
		self.processingQueue = simpy.Store(self.env)
		#this store keeps the local processed baseband signals
		self.local_processing_queue = simpy.Store(self.env)
		#self.frameProcTime = frameProcTime
		self.cpriFrameGenerationTime = cpriFrameGenerationTime
		self.transmissionTime = transmissionTime
		self.localTransmissionTime = localTransmissionTime
		self.graph = graph
		self.cpriMode = cpriMode
		#limiting coordinates of the base station area
		self.x1 = 0
		self.x2 = 0
		self.y1 = 0
		self.y2 = 0

	#this method generates users equipments
	def run(self):
		i = 0
		while True:
			yield self.env.timeout(self.distribution(self))
			#a limit for the generation of UEs for testing purposes
			if len(self.users) < 2:
				ue = UserEquipment(self.env, i, self, "Messaging", self.localTransmissionTime)
				self.users.append(ue)
				#print("{} generated UE {} at {}".format(self.aId, hash(ue), self.env.now))
				i += 1

	#every time a frame is received from a UE, keep it to generate the eCPRI frame later
	def takeFrameUE(self):
		while True:
			r = yield self.received_users_frames.get()
			self.frames.append(r)

	#this method builds a eCPRI frame and uplink transmits it to a optical network element
	def uplinkTransmitCPRI(self):
		global generatedCPRI
		frame_id = 1
		length, path = nx.single_source_dijkstra(self.graph, self.aId, "Cloud:0")#For now, cloud is the default destiny
		while True:
			yield self.env.timeout(self.cpriFrameGenerationTime)
			print("{} generating eCPRI frame {} at {}".format(self.aId, self.aId+"->"+str(frame_id), self.env.now))
			#print(psutil.virtual_memory())
			#If traditional CPRI is used, create a frame with fixed bandwidth (not implemented yet)
			activeUsers = []
			if self.cpriMode == "CPRI":
				#take each UE and put it into the CPRI frame
				if self.users:
					for i in self.users:
						activeUsers.append(i)
				#Cloud:0 is the generic destiny for tests purposes - An algorithm will be used to decide in which node it will be placed
				eCPRIFrame = ecpriFrame(self.aId+"->"+str(frame_id), None, self, "Cloud:0", activeUsers, None, None)
				if self.users:
					for i in self.users:
						i.lastLatency = i.latency
						i.latency = (i.latency + self.env.now)/frame_id
				generatedCPRI += 1
			#if eCPRI is being used, different strategy must be implemented to generate the frame
			elif self.cpriMode == "eCPRI":
				if self.users:
					for i in self.users:
						activeUsers.append(i)
				frame_size = len(activeUsers)
				eCPRIFrame = ecpriFrame(frame_id, None, self, "Cloud:0", activeUsers, None, frame_size)
				#TODO atualizar o tempo em que cada UE mandou o quadro para o RRH em função da sua distância até ele (ex. env.now - transmissiontTime,  transmissionTime vai ser dinâmico)
				if self.users:
					for i in self.users:
						i.latency = (i.latency + self.env.now)/frame_id
			#calculates the shortest path
			#length, path = nx.single_source_dijkstra(self.graph, self.aId, "Cloud:0")#For now, cloud is the default destiny
			#remove the aId of this node from the path
			eCPRIFrame.nextHop = copy.copy(path)
			eCPRIFrame.inversePath = list(eCPRIFrame.nextHop)
			eCPRIFrame.inversePath.reverse()
			eCPRIFrame.inversePath.pop(0)
			#takes the next hop
			eCPRIFrame.nextHop.pop(0)
			#print("Path for {} is {}".format(self.aId, eCPRIFrame.nextHop))
			#print("Inverse path is {}".format(eCPRIFrame.inversePath))
			destiny = elements[eCPRIFrame.nextHop.pop(0)]
			#print("{} transmitting to {}".format(self.aId, destiny.aId))
			#yield self.env.timeout(self.transmissionTime)
			destiny.processingQueue.put(eCPRIFrame)
			#update the load on the buffer of the destiny node
			destiny.currentLoad += 1
			#print("Frame {} generated".format(eCPRIFrame.aId))
			frame_id += 1

	#This method hipothetically sends an ACK to each UE. The ACK message is modeled as an update on the received time attribute of each UE.
	#The received time is update as a function of the time to send a frame to each UE regarding the distance of each UE from the RRH
	#Note that the calculation of the latency to send the frame in function of the UE position is not yet implemented
	#TODO: Implement the received time for eacj UE in function of its distance to the RRH
	def downlinkTransmitUE(self):
		frame_id = 1
		while True:
			#print(psutil.virtual_memory())
			print("{} transmitting to its UEs".format(self.aId))
			received_frame = yield self.processingQueue.get()
			#yield self.env.timeout(frameProcTime)
			#send an ack to each UE within this received eCPRI frame
			if received_frame.users:
				for i in received_frame.users:
					yield self.env.timeout(self.localTransmissionTime)
					#TODO: implement the time in which each UE receives the frame from the RRH
					#i.timeReceived[i] = self.env.now
					#TODO: Implement the jitter calculation, using the lastLatency variable
					i.jitter = (i.latency + self.env.now)/frame_id
			#update the load on the buffer after processing the frame
			self.currentLoad -= 1
			del received_frame
			#received_frame = None
			frame_id += 1

#basic network node interface to be extended by any new network class node
class ActiveNode(metaclass=abc.ABCMeta):
	def __init__(self, env, aId, aType, capacity):
		self.env = env
		self.aType = aType
		self.aId = aType+":"+str(aId)
		self.processingCapacity = capacity
		self.currentLoad = 0
		self.nextNode = None
		self.processingQueue = simpy.Store(self.env)
		self.nextNode = None
		self.lastNode = None
		self.toProcess = self.env.process(self.processRequest())

	#process each frame
	@abc.abstractmethod
	def processRequest(self):
		pass

	#transmit each frame after processing
	@abc.abstractmethod
	def sendRequest(self, request):
		pass

	#test the processing capacity
	def hasCapacity(self):
		if self.currentLoad <= self.processingCapacity:
			return True
		else:
			return False

#a general processing node
class ProcessingNode(ActiveNode):
	def __init__(self, env, aId, aType, capacity, qos, procTime, transmissionTime, graph):
		super().__init__(env, aId, aType, capacity)
		self.qos = qos#list of class of service suppoerted by this node
		self.procTime = procTime
		self.transmissionTime = transmissionTime
		self.graph = graph

	#process a request
	def processRequest(self):
		while True:
			request = yield self.processingQueue.get()
			if self.aId == request.dst:#this is the destiny node. Process it and compute the downlink path
				#print("Request {} arrived at destination {}".format(request.aId, self.aId))
				request.nextHop = request.inversePath
			print("{} buffer load is {}".format(self.aId, self.currentLoad))
			print("{} processing request {} at {}".format(self.aId, request.aId, self.env.now))
			yield self.env.timeout(self.procTime)
			#update the load on the buffer after processing the frame
			self.currentLoad -= 1
			self.sendRequest(request)

	#transmit a request to its destiny	
	def sendRequest(self, request):
		nextHop = request.nextHop.pop(0)#returns the id of the next hop
		destiny = elements[nextHop]#retrieve the next hop object searching by its id
		print("{} sending request {} to {}".format(self.aId, request.aId, destiny.aId))
		print("{} buffer load is {}".format(self.aId, self.currentLoad))
		self.env.timeout(self.transmissionTime)
		destiny.processingQueue.put(request)
		#update the load on the buffer of the destiny node
		destiny.currentLoad += 1

#a general processing node
class NetworkNode(ActiveNode):
	def __init__(self, env, aId, aType, capacity, qos, switchTime, transmissionTime, graph):
		super().__init__(env, aId, aType, capacity)
		self.qos = qos#list of class of service suppoerted by this node
		self.switchTime = switchTime
		self.transmissionTime = transmissionTime
		self.graph = graph

	#process a request
	def processRequest(self):
		while True:
			request = yield self.processingQueue.get()
			print("{} buffer load is {}".format(self.aId, self.currentLoad))
			#print("Request {} arrived at {}".format(request.aId, self.aId))
			print("{} processing request {} at {}".format(self.aId, request.aId, self.env.now))
			yield self.env.timeout(self.switchTime)
			#update the load on the buffer after processing the frame
			self.currentLoad -= 1
			#self.processingCapacity -= 1
			self.sendRequest(request)

	#transmit a request to its destiny
	def sendRequest(self, request):
		nextHop = request.nextHop.pop(0)#returns the id of the next hop
		destiny = elements[nextHop]#retrieve the next hop object searching by its id
		print("{} sending request {} to {}".format(self.aId, request.aId, destiny.aId))
		self.env.timeout(self.transmissionTime)
		destiny.processingQueue.put(request)
		#update the load on the buffer of the destiny node
		destiny.currentLoad += 1


#this class represents the control plane that will be responsible to invoke algorithms to place vBBUs and to assign wavelengths
#it will keep the representations of the topology that will be used by the algorithms, e.g., graph or ILP
#in the case of the ILP, it is necessary that every object created is represented as binary arrays for the ILP to solve it, as we did before
class ControlPlane(object):
	pass

import simpy

#--------------------------------------------------------------5GAgroSim------------------------------------------------------------------------------
# This is a simulator for agro environments supported by 5G networks

#this class represents a base sensor
class BaseSensor(object):
	def __init__(self, env, aId, aType):
		self.env = env
		self.aId = aId
		self.aType = aType
		self.packets = []
		self.start = self.env.process(self.run())

	#put the sensor to run
	def run(self):
		packetId = 0#counter to identify each generated packet in this sensor
		while True:
			yield self.env.timeout(0.5)#wait a given time to generate another packet/data
			packet = BasePacket(packetId, "Normal", 128)#128 is a hypothetical value in kb for the size of the packet (we can/may change it later)
			print("Sensor {} of Type {} generated Packet: ID {} Type {} Size {} at moment {}\n".format(self.aId, self.aType, packet.aId, packet.aType, 
																	packet.aSize, self.env.now))#self.env.now is the current time of the simulation run
			self.packets.append(packet)#append to its list of generated packet
			packetId+=1#increment the counter of packets

class SensorTemperature(BaseSensor,object):
	def __init__(self, env, aId, aType,setTemperature):
		super().__init__(env, aId, aType)
		self.setTemperature = setTemperature

	def run(self):
		packetId = 0
		while True:
			yield self.env.timeout(0.5)
			packet = BasePacket(packetId, "Temperature", 128)
			print("Sensor {} of Type {} generated Packet: ID {} Type {} at moment {} and the random number from the sensor:{} \n".format(self.aId, self.aType, packet.aId, 
																														packet.aType,self.env.now, self.setTemperature))
			self.packets.append(packet)
			packetId+=1

class SensorHumidity(BaseSensor,object):
	def __init__(self, env, aId, aType,setHumididty):
		super().__init__(env, aId, aType)
		self.setHumididty = setHumididty

	def run(self):
		packetId = 0
		while True:
			yield self.env.timeout(0.5)
			packet = BasePacket(packetId, "Humidity", 128)
			print("Sensor {} of Type {} generated Packet: ID {} Type {} at moment {} and the random number from the sensor:{} \n".format(self.aId, self.aType, packet.aId, 
																														packet.aType,self.env.now, self.setHumididty))
			self.packets.append(packet)
			packetId+=1

class SensorPh(BaseSensor,object):
	def __init__(self, env, aId, aType,setPh):
		super().__init__(env, aId, aType)
		self.setPh = setPh
		
	def run(self):
		packetId = 0
		while True:
			yield self.env.timeout(0.5)
			packet = BasePacket(packetId, "Ph", 128)
			print("Sensor {} of Type {} generated Packet: ID {} Type {} at moment {} and the random number from the sensor:{} \n".format(self.aId, self.aType, packet.aId, 
																														packet.aType,self.env.now, self.setPh))
			self.packets.append(packet)
			packetId+=1

#this class represents a base data packet
class BasePacket(object):
	def __init__(self, aId, aType, aSize):
		self.aId = aId
		self.aType = aType
		self.aSize = aSize

#---------------------------------------------------------------Running the simulation----------------------------------------------------------------
env = simpy.Environment()#sets the simpy environment
sensor1 = BaseSensor(env, 0, "Base")#create a single base sensor
sensor2 = BaseSensor(env, 1, "Base")
sensor_Temperature = SensorTemperature(env, 0, "Temperature",random.randrange(0, 40))#create temperature sensor
sensor_Humidity = SensorHumidity(env, 0, "Humididty",random.randrange(0, 60))#create Humidity sensor
sensor_Ph = SensorPh(env, 0, "Ph",random.randrange(0, 14))#create Ph sensor
print("---------------------------------------------Starting simulation---------------------------------------------")
env.run(3600)#sets the simulation to run for 3600 units of time (we can consider it as seconds) and starts the simulation
print("----------------------------------------------Ending simulation----------------------------------------------")
