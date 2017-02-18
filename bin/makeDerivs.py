"""

Calculates cluster count derivatives using MPI.

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


comm = MPI.COMM_WORLD
rank = comm.Get_rank()
numcores = comm.Get_size()    




# the boss prepares cosmology objects for the minions
# Also, I really don't want all my cores to import a bunch of
# python modules
if rank==0:

    import sys
    from ConfigParser import SafeConfigParser 
    import cPickle as pickle
    import numpy as np

    inParamList = sys.argv[1].split(',')
    expName = sys.argv[2]
    calName = sys.argv[3]
    calFile = sys.argv[4]

    # Let's read in all parameters that can be varied by looking
    # for those that have step sizes specified. All the others
    # only have fiducials.
    iniFile = "input/pipelineMakeDerivs.ini"
    Config = SafeConfigParser()
    Config.optionxform=str
    Config.read(iniFile)

    paramList = [] # the parameters that can be varied
    fparams = {}   # the 
    stepSizes = {}
    for (key, val) in Config.items('params'):
        if ',' in val:
            param, step = val.split(',')
            paramList.append(key)
            fparams[key] = float(param)
            stepSizes[key] = float(step)
        else:
            fparams[key] = float(val)



    if inParamList[0]=="allParams":
        assert len(inParamList)==1, "I'm confused why you'd specify more params with allParams."
        
        inParamList = paramList

    else:
        for param in inParamList:
            assert param in paramList, param + " not found in ini file with a specified step size."
            assert param in stepSizes.keys(), param + " not found in stepSizes dict. Looks like a bug in the code."
    

    numParams = len(inParamList)
    neededCores = 2*numParams+1
    assert numcores==neededCores, "I need 2N+1 cores to do my job for N params. \
    You gave me "+str(numcores)+ " core(s) for "+str(numParams)+" param(s)."


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
    lknee = Config.getfloat(expName,'lknee')
    alpha = Config.getfloat(expName,'alpha')

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
if rank==0: print "Broadcasted."

myParamIndex = (rank+1)/2-1
passParams = fparams.copy()


# If boss, do the fiducial. If odd rank, the minion is doing an "up" job, else doing a "down" job
if rank ==0:
    myParam = "fid"
    upDown = ""
elif rank%2==1:
    myParam = inParamList[myParamIndex]
    passParams[myParam] = fparams[myParam] + stepSizes[myParam]/2.
    upDown = "_up"

elif rank%2==0:
    myParam = inParamList[myParamIndex]
    passParams[myParam] = fparams[myParam] - stepSizes[myParam]/2.
    upDown = "_down"

print rank,myParam,upDown
cc = ClusterCosmology(passParams,constDict,clTTFixFile=clttfile)
HMF = Halo_MF(clusterCosmology=cc)
dN_dmqz = HMF.N_of_mqz_SZ(lndM,zrange,mexprange,qbins,beam,noise,freq,clusterDict,lknee,alpha)
np.save("data/dN_dzmq_"+saveId+"_"+myParam+upDown,dN_dmqz)

    
