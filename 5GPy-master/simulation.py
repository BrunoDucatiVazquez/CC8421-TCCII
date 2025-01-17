#this is the simulation module, in which the simulation parameters and the simulation itself is initiated
from mimetypes import init
import simpy
from sympy import banded
import network
import psutil
import utility as util
import networkx as nx
import simpy
import functools
import random as np
import time
from enum import Enum
from scipy.stats import norm


#simpy environment variable
env = simpy.Environment()
#reads the XML configuration file
parameters = util.xmlParser('configurations.xml')

#initiate input parameters from the entries on the XML file
switchTime = float(parameters["InputParameters"].find("switchTime").text)
frameProcTime = float(parameters["InputParameters"].find("frameProcTime").text)
transmissionTime = float(parameters["InputParameters"].find("transmissionTime").text)
localTransmissionTime = float(parameters["InputParameters"].find("localTransmissionTime").text)
cpriFrameGenerationTime = float(parameters["InputParameters"].find("cpriFrameGenerationTime").text)
distributionAverage = float(parameters["InputParameters"].find("distributionAverage").text)
cpriMode = parameters["InputParameters"].find("cpriMode").text
distribution = lambda x: np.expovariate(1000)
limitAxisY = int(parameters["InputParameters"].find("limitAxisY").text)#limit of axis Y of the network topology on a cartesian plane
limitAxisX = int(parameters["InputParameters"].find("limitAxisX").text)#limit of axis X of the network topology on a cartesian plane
stepAxisY = int(parameters["InputParameters"].find("stepAxisY").text)#increasing step on axis Y when defining the size of the base station
stepAxisX = int(parameters["InputParameters"].find("stepAxisX").text)#increasing step on axis X when defining the size of the base station

#keep the input parameters for visualization or control purposes
inputParameters = []
for p in parameters["InputParameters"]:
	inputParameters.append(p)

#get the attributes of each RRH
rrhsParameters = []
for r in parameters["RRHs"]:
	rrhsParameters.append(r.attrib)

#get the attributes of each node to be created
netNodesParameters = []
for node in parameters["NetworkNodes"]:
	netNodesParameters.append(node.attrib)

#get the attributes of each processing node to be created
procNodesParameters = []
for proc in parameters["ProcessingNodes"]:
	procNodesParameters.append(proc.attrib)

#get the edges for the graph representation
networkEdges = []
for e in parameters["Edges"]:
	networkEdges.append(e.attrib)

#save the id of each element to create the graph
vertex = []
#RRHs
for r in rrhsParameters:
	vertex.append("RRH:"+str(r["aId"]))
#Network nodes
for node in netNodesParameters:
	vertex.append(node["aType"]+":"+str(node["aId"]))
#Processing nodes
for proc in procNodesParameters:
	vertex.append(proc["aType"]+":"+str(node["aId"]))

#create the graph
G = nx.Graph()
#add the nodes to the graph
for u in vertex:
	G.add_node(u)
#add the edges and weights to the graph
for edge in networkEdges:
	G.add_edge(edge["source"], edge["destiny"], weight= float(edge["weight"]))

#create the elements
#create the RRHs
for r in rrhsParameters:
	rrh = network.RRH(env, r["aId"], distribution, cpriFrameGenerationTime, transmissionTime, localTransmissionTime, G, cpriMode)
	network.elements[rrh.aId] = rrh

#create the network nodes
for node in netNodesParameters:
	net_node = network.NetworkNode(env, node["aId"], node["aType"], float(node["capacity"]), node["qos"], switchTime, transmissionTime, G)
	network.elements[net_node.aId] = net_node

#create the processing nodes
for proc in procNodesParameters:
	proc_node = network.ProcessingNode(env, proc["aId"], proc["aType"], float(proc["capacity"]), proc["qos"], frameProcTime, transmissionTime, G)
	network.elements[proc_node.aId] = proc_node

#print(network.elements.keys())

#set the limit area of each base station
util.createNetworkLimits(limitAxisX, limitAxisY, stepAxisX, stepAxisY, network.elements)

#print the coordinate of each base station
util.printBaseStationCoordinates(rrhsParameters, network.elements)


#starts the simulation
print("------------------------------------------------------------SIMULATION STARTED AT {}------------------------------------------------------------".format(env.now))
env.run(until = 3600)
print("------------------------------------------------------------SIMULATION ENDED AT {}------------------------------------------------------------".format(env.now))
print(psutil.virtual_memory())#print the memory consumption for testing
#print("Total of CPRI basic frames: {}".format(network.generatedCPRI))

'''
#Tests
#print the graph
#print([i for i in nx.edges(G)])
print(G.edges())
#print(G["RRH:0"]["Switch:0"]["weight"])
#print(G.graph)
#for i in nx.edges(G):
#	print("{} --> {} Weight: {}".format(i[0], i[1], G[i[0]][i[1]]["weight"]))

#calling Dijkstra to calculate the shortest path. Returning variables "length" and "path" are the total cost of the path and the path itself, respectively
#length, path = nx.single_source_dijkstra(G, "RRH:0", "Cloud:0")
#print(path)

#for i in range(len(rrhs)):
#  print(g["s"]["RRH{}".format(i)]["capacity"])


print("-----------------Input Parameters-------------------")
for i in inputParameters:
	print("{}: {}".format(i.tag, i.text))

print("-----------------RRHs-------------------")
for i in rrhsParameters:
	print(i)

print("-----------------Network Nodes-------------------")
for i in netNodesParameters:
	print(i)

print("-----------------Processing Nodes-------------------")
for i in procNodesParameters:
	print(i)

print("-----------------Edges-------------------")
for i in networkEdges:
	print(i)
'''


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



