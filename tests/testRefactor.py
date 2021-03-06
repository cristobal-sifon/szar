from __future__ import print_function
from __future__ import division
from past.utils import old_div
import matplotlib
matplotlib.use('Agg')
import camb
import numpy as np
from scipy import special
import matplotlib.pyplot as plt
import sys, os, time
from szar.counts import ClusterCosmology,SZ_Cluster_Model,Halo_MF,getTotN
from orphics.tools.io import Plotter,dictFromSection,listFromConfig
from configparser import SafeConfigParser 
import pickle as pickle
from orphics.tools.io import Plotter
from orphics.analysis.flatMaps import interpolateGrid

clusterParams = 'LACluster' # from ini file
cosmologyName = 'LACosmology' # from ini file
experimentName = "LATest"

iniFile = "input/params.ini"
Config = SafeConfigParser()
Config.optionxform=str
Config.read(iniFile)

outDir=os.environ['WWW']

beam = listFromConfig(Config,experimentName,'beams')
noise = listFromConfig(Config,experimentName,'noises')
freq = listFromConfig(Config,experimentName,'freqs')
lmax = int(Config.getfloat(experimentName,'lmax'))
lknee = Config.getfloat(experimentName,'lknee')
alpha = Config.getfloat(experimentName,'alpha')
fsky = Config.getfloat(experimentName,'fsky')


cosmoDict = dictFromSection(Config,cosmologyName)
constDict = dictFromSection(Config,'constants')
clusterDict = dictFromSection(Config,clusterParams)
cc = ClusterCosmology(cosmoDict,constDict,clTTFixFile = "data/cltt_lensed_Feb18.txt")#,skipCls=True)


mfile = "data/S4-7mCMB_all.pkl"
minrange, zinrange, lndM = pickle.load(open(mfile,'rb'))


# zs = np.arange(0.5,3.0,0.5)
# Mexp = np.arange(13.5,15.7,0.5)

# zs = np.arange(0.1,3.0,0.3)
# Mexp = np.arange(13.0,15.7,0.3)

#zs = np.arange(0.1,3.0,0.1)
w = 0.1
z_edges = np.arange(0.,3.0+w,w)
zs = old_div((z_edges[1:]+z_edges[:-1]),2.)

w = 0.1
Mexp_edges = np.arange(13.0,15.7+w,w)
M_edges = 10**Mexp_edges
M = old_div((M_edges[1:]+M_edges[:-1]),2.)
Mexp = np.log10(M)

outmerr = interpolateGrid(lndM,minrange,zinrange,Mexp,zs,regular=False,kind="cubic",bounds_error=False,fill_value=np.inf)




hmf = Halo_MF(cc,Mexp_edges,z_edges)


SZProf = SZ_Cluster_Model(cc,clusterDict,rms_noises = noise,fwhms=beam,freqs=freq,lknee=lknee,alpha=alpha)

fsky = 0.4

N1 = hmf.N_of_z()*fsky

#hmf.sigN = np.loadtxt("temp.txt")

try:
    hmf.sigN = np.loadtxt("tempSigN.txt")
    N2 = hmf.N_of_z_SZ(SZProf)*fsky
except:
    N2 = hmf.N_of_z_SZ(SZProf)*fsky
    np.savetxt("tempSigN.txt",hmf.sigN)

pl = Plotter()
pl.plot2d(hmf.sigN)
pl.done(outDir+"signRefactor.png")
    
pl = Plotter(scaleY='log')
pl.add(zs,N1)
pl.add(zs,N2)

Ntot1 = np.trapz(N2,zs)
print(Ntot1)


sn,ntot = hmf.Mass_err(fsky,outmerr,SZProf)

print(ntot)



#q_arr = np.logspace(np.log10(6.),np.log10(500.),64)
qs = [6.,500.,64]
qbin_edges = np.logspace(np.log10(qs[0]),np.log10(qs[1]),int(qs[2])+1)
q_arr = old_div((qbin_edges[1:]+qbin_edges[:-1]),2.)

dnqmz = hmf.N_of_mqz_SZ(outmerr,qbin_edges,SZProf)

print((qbin_edges.shape))
print((dnqmz.shape))
N,Nofz = getTotN(dnqmz,Mexp_edges,z_edges,qbin_edges,returnNz=True)

print((N*fsky))

pl.add(zs,Nofz*fsky,label="mqz")
pl.legendOn()
pl.done(outDir+"nsRefactor.png")


nnoq = np.trapz(dnqmz,q_arr,axis=2)*fsky
pl = Plotter()
pl.plot2d(nnoq)
pl.done(outDir+"ngridRefactor.png")
