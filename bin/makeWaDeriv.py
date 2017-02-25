"""

Calculates cluster count derivatives for w_a using MPI.

Always reads values from input/pipelineMakeDerivs.py, including
parameter fiducials and step-sizes.

python bin/makeDerivs.py <paramList> <expName> <calName> <calFile>

<paramList> is comma separated param list, no spaces, case-sensitive.

If <paramList> is "allParams", calculates derivatives for all
params with step sizes in [params] section of ini file.

<expName> is name of section in input/pipelineMakeDerivs.py
that specifies an experiment.

<calName> name of calibration that will be used in the saved files

<calFile> is the name of a pickle file containing the mass
calibration error over mass.

"""

from mpi4py import MPI
from szlib.szcounts import ClusterCosmology,Halo_MF
import numpy as np
    

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
numcores = comm.Get_size()    

assert numcores==3


# the boss prepares cosmology objects for the minions
# Also, I really don't want all my cores to import a bunch of
# python modules
if rank==0:

    import sys
    from ConfigParser import SafeConfigParser 
    import cPickle as pickle

    expName = sys.argv[1]
    calName = sys.argv[2]
    calFile = sys.argv[3]

    # Let's read in all parameters that can be varied by looking
    # for those that have step sizes specified. All the others
    # only have fiducials.
    iniFile = "input/pipeline.ini"
    Config = SafeConfigParser()
    Config.optionxform=str
    Config.read(iniFile)

    paramList = [] # the parameters that can be varied
    fparams = {}   # the 
    for (key, val) in Config.items('params'):
        if ',' in val:
            param, step = val.split(',')
            paramList.append(key)
            fparams[key] = float(param)
            stepSizes[key] = float(step)
        else:
            fparams[key] = float(val)




    numParams = 1


    suffix = Config.get('general','suffix')
    # load the mass calibration grid
    mexprange, zrange, lndM = pickle.load(open(calFile,"rb"))


    zrange = np.insert(zrange,0,0.0)
    saveId = expName + "_" + calName + "_" + suffix

    from orphics.tools.io import dictFromSection, listFromConfig
    constDict = dictFromSection(Config,'constants')
    clusterDict = dictFromSection(Config,'cluster_params')
    beam = listFromConfig(Config,expName,'beams')
    noise = listFromConfig(Config,expName,'noises')
    freq = listFromConfig(Config,expName,'freqs')
    lknee = listFromConfig(Config,expName,'lknee')[0]
    alpha = listFromConfig(Config,expName,'alpha')[0]

    clttfile = Config.get('general','clttfile')

    # get s/n q-bins
    qs = listFromConfig(Config,'general','qbins')
    qspacing = Config.get('general','qbins_spacing')
    if qspacing=="log":
        qbins = np.logspace(np.log10(qs[0]),np.log10(qs[1]),int(qs[2]))
    elif qspacing=="linear":
        qbins = np.linspace(qs[0],qs[1],int(qs[2]))
    else:
        raise ValueError

    massMultiplier = Config.getfloat('general','mass_calib_factor')

else:
    inParamList = None
    stepSizes = None
    fparams = None
    mexprange = None
    zrange = None
    lndM = None
    saveId = None
    constDict = None
    clttfile = None
    qbins = None
    clusterDict = None
    beam = None
    noise = None
    freq = None
    lknee = None
    alpha = None
    massMultiplier = None

if rank==0: print "Broadcasting..."
inParamList = comm.bcast(inParamList, root = 0)
stepSizes = comm.bcast(stepSizes, root = 0)
fparams = comm.bcast(fparams, root = 0)
mexprange = comm.bcast(mexprange, root = 0)
zrange = comm.bcast(zrange, root = 0)
lndM = comm.bcast(lndM, root = 0)
saveId = comm.bcast(saveId, root = 0)
constDict = comm.bcast(constDict, root = 0)
clttfile = comm.bcast(clttfile, root = 0)
qbins = comm.bcast(qbins, root = 0)
clusterDict = comm.bcast(clusterDict, root = 0)
beam = comm.bcast(beam, root = 0)
noise = comm.bcast(noise, root = 0)
freq = comm.bcast(freq, root = 0)
lknee = comm.bcast(lknee, root = 0)
alpha = comm.bcast(alpha, root = 0)
massMultiplier = comm.bcast(massMultiplier, root = 0)
if rank==0: print "Broadcasted."

myParamIndex = (rank+1)/2-1
passParams = fparams.copy()


# If boss, do the fiducial. If odd rank, the minion is doing an "up" job, else doing a "down" job
if rank==0:
    pass
elif rank%2==1:
    myParam = inParamList[myParamIndex]
    passParams[myParam] = fparams[myParam] + stepSizes[myParam]/2.
elif rank%2==0:
    myParam = inParamList[myParamIndex]
    passParams[myParam] = fparams[myParam] - stepSizes[myParam]/2.


if rank!=0: print rank,myParam,fparams[myParam],passParams[myParam]
cc = ClusterCosmology(passParams,constDict,clTTFixFile=clttfile)
HMF = Halo_MF(clusterCosmology=cc)
dN_dmqz = HMF.N_of_mqz_SZ(lndM*massMultiplier,zrange,mexprange,qbins,beam,noise,freq,clusterDict,lknee,alpha)

if rank==0: 
    np.save("data/N_dzmq_"+saveId+"_fid",dN_dmqz)
    dUps = {}
    dDns = {}

    print "Waiting for ups and downs..."
    for i in range(1,numcores):
        data = np.empty(dN_dmqz.shape, dtype=np.float64)
        comm.Recv(data, source=i, tag=77)
        myParamIndex = (i+1)/2-1
        if i%2==1:
            dUps[inParamList[myParamIndex]] = data.copy()
        elif i%2==0:
            dDns[inParamList[myParamIndex]] = data.copy()

    for param in inParamList:
        dN = (dUps[param]-dDns[param])/stepSizes[param]
        np.save("data/dNup_dzmq_"+saveId+"_"+param,dUps[param])
        np.save("data/dNdn_dzmq_"+saveId+"_"+param,dDns[param])
        np.save("data/dN_dzmq_"+saveId+"_"+param,dN)
        
else:
    data = dN_dmqz.astype(np.float64)
    comm.Send(data, dest=0, tag=77)




    