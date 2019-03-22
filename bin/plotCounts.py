from __future__ import print_function
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from configparser import SafeConfigParser
from orphics.io import Plotter
import pickle as pickle
import sys

from szar.counts import ClusterCosmology,Halo_MF,getNmzq
from szar.szproperties import SZ_Cluster_Model
import numpy as np

from orphics.maps import interpolate_grid

def resample_bin(d, factors=[0.5], axes=None):
	if np.allclose(factors,1): return d
	down = [max(1,int(round(1/f))) for f in factors]
	up   = [max(1,int(round(f)))   for f in factors]
	d    = downsample_bin(d, down, axes)
	return upsample_bin  (d, up, axes)

def downsample_bin(d, steps=[2], axes=None):
	assert len(steps) <= d.ndim
	if axes is None: axes = np.arange(-1,-len(steps)-1,-1)
	assert len(axes) == len(steps)
	# Expand steps to cover every axis in order
	fullsteps = np.zeros(d.ndim,dtype=int)+1
	for ax, step in zip(axes, steps): fullsteps[ax]=step
	# Make each axis an even number of steps to prepare for reshape
	s = tuple([slice(0,L/step*step) for L,step in zip(d.shape,fullsteps)])
	d = d[s]
	# Reshape each axis to L/step,step to prepare for mean
	newshape = np.concatenate([[L/step,step] for L,step in zip(d.shape,fullsteps)])
	d = np.reshape(d, newshape)
	# And finally take the mean over all the extra axes
	return np.sum(d, tuple(range(1,d.ndim,2)))

def upsample_bin(d, steps=[2], axes=None):
	shape = d.shape
	assert len(steps) <= d.ndim
	if axes is None: axes = np.arange(-1,-len(steps)-1,-1)
	assert len(axes) == len(steps)
	# Expand steps to cover every axis in order
	fullsteps = np.zeros(d.ndim,dtype=int)+1
	for ax, step in zip(axes, steps): fullsteps[ax]=step
	# Reshape each axis to (n,1) to prepare for tiling
	newshape = np.concatenate([[L,1] for L in shape])
	d = np.reshape(d, newshape)
	# And tile
	d = np.tile(d, np.concatenate([[1,s] for s in fullsteps]))
	# Finally reshape back to proper dimensionality
	return np.reshape(d, np.array(shape)*np.array(fullsteps))

#outDir = "/gpfs01/astro/www/msyriac/web/work/"
outDir = "/Users/nab/Desktop/"


iniFile = "input/pipeline.ini"
Config = SafeConfigParser()
Config.optionxform=str
Config.read(iniFile)
bigDataDir = Config.get('general','bigDataDirectory')
clttfile = Config.get('general','clttfile')

gridName = "grid-owl2"
#gridName = "grid-default"
#version = "0.3_ysig_0.127"
version = ["1.0","1.1"]#"0.7"
cal = "owl2"#"CMB_all"
#cal = "CMB_all_PICO"
#cal = "CMB_pol_miscentered"

from orphics.io import dict_from_section, list_from_config
constDict = dict_from_section(Config,'constants')
clusterDict = dict_from_section(Config,'cluster_params')

fparams = {}   # the 
for (key, val) in Config.items('params'):
    if ',' in val:
        param, step = val.split(',')
        fparams[key] = float(param)
    else:
        fparams[key] = float(val)


cc = ClusterCosmology(fparams,constDict,clTTFixFile=clttfile)

from matplotlib.patches import Rectangle


#expList = ['CMB-Probe-v3-1']
#expList = ['S4-1.0-CDT','S4-1.5-CDT']#,'S4-2.0-0.4','S4-2.5-0.4','S4-3.0-0.4']
#expList = ['S4-1.0-0.4','S4-1.5-0.4','S4-2.0-0.4','S4-2.5-0.4','S4-3.0-0.4']
#expList = ['S4-2.0-0.4']#,'S4-1.5-0.4','S4-1.5-0.3','S4-1.5-0.2','S4-1.5-0.1','S4-1.5-0.05']
#expList = ['S4-1.0-0.4','S4-1.5-0.4','S4-2.0-0.4','S4-2.5-0.4','S4-3.0-0.4']
#expList = ['SO-v3-goal-40','SO-v3-base-40']#,'SO-v3-goal-20','SO-v3-base-20','SO-v3-goal-10','SO-v3-base-10']
expList = ['CMB-Probe-v4-CBE','CMB-Probe-v4-REQ']
expList = ['SO-v3-goal-40','SO-v3-goal-40']

pad = 0.05

pl = Plotter(xlabel="$z$",ylabel="$N(z)$",ftsize=12,yscale='log')
#pl = Plotter(labelX="$z$",labelY="$N(z)$",ftsize=12)

colList = ['C0','C1','C2','C3','C4','C5']
for expName,col,ver in zip(expList,colList,version):

    mgrid,zgrid,siggrid = pickle.load(open(bigDataDir+"szgrid_"+expName+"_"+gridName+ "_v" + ver+".pkl",'rb'))

#for expName,col in zip(expList,colList):

#    mgrid,zgrid,siggrid = pickle.load(open(bigDataDir+"szgrid_"+expName+"_"+gridName+ "_v" + version+".pkl",'rb'))

    if (cal == 'owl2'):    
	    massGridName = bigDataDir+"lensgrid_grid-"+cal+"_"+cal+".pkl"
    else:
	    massGridName = bigDataDir+"lensgrid_"+expName+"_"+gridName+"_"+cal+ "_v" + version+".pkl"
	    

    mexp_edges, z_edges, lndM = pickle.load(open(massGridName,"rb"))

    zrange = (z_edges[1:]+z_edges[:-1])/2.

    beam = list_from_config(Config,expName,'beams')
    noise = list_from_config(Config,expName,'noises')
    freq = list_from_config(Config,expName,'freqs')
    lknee = list_from_config(Config,expName,'lknee')[0]
    alpha = list_from_config(Config,expName,'alpha')[0]
    fsky = Config.getfloat(expName,'fsky')
    HMF = Halo_MF(cc,mexp_edges,z_edges)
    HMF.sigN = siggrid.copy()

    
    SZProf = SZ_Cluster_Model(cc,clusterDict,rms_noises = noise,fwhms=beam,freqs=freq,lknee=lknee,alpha=alpha)
    Nofzs = np.multiply(HMF.N_of_z_SZ(fsky,SZProf),np.diff(z_edges).reshape(1,z_edges.size-1)).ravel()
    print(Nofzs.sum())
    #sys.exit()

    saveId = expName + "_" + gridName + "_" + cal + "_v" + ver
    Nmzq = np.load(bigDataDir+"N_mzq_"+saveId+"_fid.npy")*fsky
    Nmz = Nmzq.sum(axis=-1)
    Nz = Nmzq.sum(axis=0).sum(axis=-1)
    print(Nz.shape)


    m_edges = 10**mexp_edges
    masses = (m_edges[1:]+m_edges[:-1])/2.
    mexp_new = np.log10(np.linspace(masses[0],masses[-1],10))
    z_new = np.linspace(0.25,2.75,10)
    print(Nmz.sum())
    rn = resample_bin(Nmz,factors=[float(mexp_new.size)/Nmz.shape[0],float(z_new.size)/Nmz.shape[1]],axes=[-2,-1])

    currentAxis = plt.gca()

    testcount = 0.

    zbins = z_edges #np.arange(0.,3.5,0.5)
    for zleft,zright in zip(zbins[:-1],zbins[1:]):
        zcent = (zleft+zright)/2.
        xerr = (zright-zleft)/2.
        N = Nofzs[np.logical_and(zrange>zleft,zrange<=zright)].sum()
        print(zcent,N)
	testcount += N
        N2 = Nz[np.logical_and(zrange>zleft,zrange<=zright)].sum()
        currentAxis.add_patch(Rectangle((zcent - xerr+pad, 0), 2*xerr-pad/2., N, facecolor=col))#,alpha=0.5))
        #currentAxis.add_patch(Rectangle((zcent - xerr+pad+pad/3., 0), 2*xerr-pad/2., N2, facecolor=col))
    pl.add([0,0],[0,0],ls='-',linewidth=4,label=expName,color=col)
    massSense = lndM #*100./np.sqrt(Nmz)
    massSense = interpolate_grid(massSense,masses,zrange,10**mexp_new,z_new,regular=True)#,kind="cubic",bounds_error=False,fill_value=np.inf)
    print((massSense.shape),testcount)
    fsense = massSense/np.sqrt(rn)
    
    

pl.legend(labsize=9,loc='upper right')
pl._ax.set_ylim(1,5.e4) # fsky
pl._ax.set_xlim(0.,3.)
pl.done(outDir+"clNofz.pdf")

fsense[fsense>10.] = np.nan
from orphics.io import Plotter
import os
mmin = mgrid.min()
mmax = mgrid.max()
zmin = zgrid.min()
zmax = zgrid.max()
pgrid = np.rot90((fsense))
pl = Plotter(xlabel="$\\mathrm{log}_{10}(M)$",ylabel="$z$",ftsize=14)
pl.plot2d(pgrid,extent=[mmin,mmax,zmin,zmax],labsize=14,aspect="auto",lim=[0.,10.])
pl.done(outDir+"massSense.png")

rn[rn<1]=np.nan
mmin = mgrid.min()
mmax = mgrid.max()
zmin = zgrid.min()
zmax = zgrid.max()
pgrid = np.rot90((rn))
pl = Plotter(labelX="$\\mathrm{log}_{10}(M)$",labelY="$z$",ftsize=14)
pl.plot2d(pgrid,extent=[mmin,mmax,zmin,zmax],labsize=14,aspect="auto")
pl.done(outDir+"rn.png")


#rn[rn<1]=np.nan
mmin = mgrid.min()
mmax = mgrid.max()
zmin = zgrid.min()
zmax = zgrid.max()
pgrid = np.rot90((massSense))
pl = Plotter(labelX="$\\mathrm{log}_{10}(M)$",labelY="$z$",ftsize=14)
pl.plot2d(pgrid,extent=[mmin,mmax,zmin,zmax],labsize=14,aspect="auto")
pl.done(outDir+"lndm.png")


