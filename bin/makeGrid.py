from __future__ import print_function
from __future__ import division
from builtins import str
from builtins import range
from past.utils import old_div
import matplotlib
matplotlib.use('Agg')
from mpi4py import MPI
import numpy as np
from orphics.lensing import NFWMatchedFilterSN
from szar.counts import ClusterCosmology,Halo_MF
from szar.szproperties import SZ_Cluster_Model
import szar.fisher as sfisher
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
numcores = comm.Get_size()    

# Hacky fix to python 2 vs 3 problem. Should return desired results in both versions when comparing floats to None
def check_pzcut_less(a, pzcut):
    if pzcut is None:
        return True
    elif a > pzcut:
        return True
    else:
        return False

if rank == 0:
    import sys
    from configparser import SafeConfigParser 
    import pickle as pickle
    import argparse

    parser = argparse.ArgumentParser(description='Make an M,z grid using MPI. Currently implements CMB lensing \
    matched filter and SZ variance.')
    parser.add_argument('expName', type=str,help='The name of the experiment in input/pipeline.ini')
    parser.add_argument('gridName', type=str,help='The name of the grid in input/pipeline.ini')
    parser.add_argument('lensName', nargs='?',type=str,help='The name of the CMB lensing calibration in input/pipeline.ini. Not required if using --skip-lensing option.',default="")
    parser.add_argument("-l", "--lknee",type=float,help='Optional lknee_T override.',default=None)
    parser.add_argument("-a", "--alpha",type=float,help='Optional alpha_T override.',default=None)
    parser.add_argument('--skip-lensing', dest='skipLens', action='store_const', \
                        const=True, default=False, \
                        help='Skip CMB lensing matched filter.')

    parser.add_argument('--skip-sz', dest='skipSZ', action='store_const', \
                        const=True, default=False, \
                        help='Skip SZ variance.')
    # #parser.add_argument('--skip-ray', dest='skipRay', action='store_const',
    #                     const=True, default=False,
    #                     help='Skip miscentered lensing.')

    
    args = parser.parse_args()


    expName = args.expName
    gridName = args.gridName
    lensName = args.lensName
    lkneeTOverride = args.lknee
    alphaTOverride = args.alpha

    suffix = ""
    if lkneeTOverride is not None:
        suffix += "_"+str(lkneeTOverride)
        print("Overriding lknee with ", lkneeTOverride)
    if alphaTOverride is not None:
        suffix += "_"+str(alphaTOverride)
        print("Overriding alpha with ", alphaTOverride)

    
    #doRayDeriv = not(args.skipRay)
    doLens = not(args.skipLens)
    doSZ = not(args.skipSZ)


    if doLens: assert lensName!="", "ERROR: You didn't specify a lensName. If you don't want to do lensing, add --skip-lensing."

    assert doLens or doSZ, "ERROR: Nothing to do."





    iniFile = "input/pipeline.ini"
    Config = SafeConfigParser()
    Config.optionxform=str
    Config.read(iniFile)
    version = Config.get('general','version')
    pzcut = Config.getfloat('general','photoZCutOff')

    fparams = {}   
    for (key, val) in Config.items('params'):
        if ',' in val:
            param, step = val.split(',')
            if key=='sigR':
                rayFid = float(param)
                rayStep = float(step)
            fparams[key] = float(param)
        else:
            fparams[key] = float(val)

    from orphics.io import dict_from_section, list_from_config

    bigDataDir = Config.get('general','bigDataDirectory')

    ms = list_from_config(Config,gridName,'mexprange')
    Mexp_edges = np.arange(ms[0],ms[1]+ms[2],ms[2])
    zs = list_from_config(Config,gridName,'zrange')
    z_edges = np.arange(zs[0],zs[1]+zs[2],zs[2])


    M_edges = 10**Mexp_edges
    M = old_div((M_edges[1:]+M_edges[:-1]),2.)
    mgrid = np.log10(M)

    zgrid = old_div((z_edges[1:]+z_edges[:-1]),2.)

    
    beam = list_from_config(Config,expName,'beams')
    noise = list_from_config(Config,expName,'noises')
    freq = list_from_config(Config,expName,'freqs')
    fsky = Config.getfloat(expName,'fsky')
    try:
        v3mode = Config.getint(expName,'V3mode')
    except:
        v3mode = -1

    lkneeT,lkneeP = list_from_config(Config,expName,'lknee')
    if lkneeTOverride is not None: lkneeT = lkneeTOverride
    alphaT,alphaP = list_from_config(Config,expName,'alpha')
    if alphaTOverride is not None: alphaT = alphaTOverride
    tellmin,tellmax = list_from_config(Config,expName,'halo_tellrange')
    pellmin,pellmax = list_from_config(Config,expName,'halo_pellrange')
    try:
        doFg = Config.getboolean(expName,'do_foregrounds')
    except:
        print("NO FG OPTION FOUND IN INI. ASSUMING TRUE.")
        doFg = True

    try:
        dotsz_cib = Config.getboolean(expName,'do_tsz_cib')
    except:
        print("NO tSZ_CIB OPTION FOUND IN INI. ASSUMING TRUE.")
        dotsz_cib = True

    lmax = int(Config.getfloat(expName,'lmax'))
    constDict = dict_from_section(Config,'constants')

    if doLens:

        if v3mode>-1:
            #     0: threshold, 
            #     1: baseline, 
            #     2: goal

            v3mode_fudge = 2 #HACK
            fstr_fudge = 40 #HACK
            senstr = ['threshold','base','goal'][v3mode_fudge]
            fstr = expName[-2:]
            #fskystr = {'10':'4000','20':'8000','40':'16000'}[fstr_fudge]
            fskystr = '16000'

            ls,Nls,_ = np.loadtxt(bigDataDir+"so_v3_halo_lensing_nmv_%s_%s.txt" % (senstr,fskystr),unpack=True)
            print("=== Loaded SO Halo Lensing Noise ===")
        else:
            pols = Config.get(lensName,'polList').split(',')
            miscentering = Config.getboolean(lensName,'miscenter')
            delens = Config.getboolean(lensName,'delens')
            freq_to_use = Config.getfloat(lensName,'freq')
            ind = np.where(np.isclose(freq,freq_to_use))
            beamFind = np.array(beam)[ind]
            noiseFind = np.array(noise)[ind]
            assert beamFind.size==1
            assert noiseFind.size==1


            testFreq = freq_to_use
            from szar.foregrounds import fgNoises
            fgs = fgNoises(constDict,ksz_battaglia_test_csv="data/ksz_template_battaglia.csv",tsz_battaglia_template_csv="data/sz_template_battaglia.csv")
            tcmbmuk = constDict['TCMB'] * 1.0e6
            ksz = lambda x: fgs.ksz_temp(x)/x/(x+1.)*2.*np.pi/ tcmbmuk**2.
            radio = lambda x: fgs.rad_ps(x,testFreq,testFreq)/x/(x+1.)*2.*np.pi/ tcmbmuk**2.
            cibp = lambda x: fgs.cib_p(x,testFreq,testFreq) /x/(x+1.)*2.*np.pi/ tcmbmuk**2.
            cibc = lambda x: fgs.cib_c(x,testFreq,testFreq)/x/(x+1.)*2.*np.pi/ tcmbmuk**2.
            tsz = lambda x: fgs.tSZ(x,testFreq,testFreq)/x/(x+1.)*2.*np.pi/ tcmbmuk**2.

            fgFunc =  lambda x: ksz(x)+radio(x)+cibp(x)+cibc(x)+tsz(x)

            beamTX = 5.0
            noiseTX = 42.0
            tellminX = 2
            tellmaxX = 3000
            lkneeTX = 0
            alphaTX = 1
            fgFuncX = None


            beamPX = beamTY = beamPY = beamFind
            beamY = beamTY
            noiseTY = noiseFind
            noisePX = np.sqrt(2.)*noiseTY
            noisePY = np.sqrt(2.)*noiseTY
            pellminX = pellmin
            pellmaxX = pellmax
            pellminY = pellmin
            pellmaxY = pellmax
            tellminY = tellmin
            tellmaxY = tellmax
            lkneeTY = lkneeT
            lkneePX = lkneePY = lkneeP
            alphaTY = alphaT
            alphaPX = alphaPY = alphaP
            if doFg:
                fgFuncY = fgFunc
            else:
                fgFuncY = None


            import flipper.liteMap as lm
            from alhazen.quadraticEstimator import NlGenerator,getMax
            deg = 5.
            px = 1.0
            dell = 10
            gradCut = 2000
            kellmin = 10
            lmap = lm.makeEmptyCEATemplate(raSizeDeg=deg, decSizeDeg=deg,pixScaleXarcmin=px,pixScaleYarcmin=px)
            kellmax = max(tellmax,pellmax)
            from orphics.cosmology import Cosmology
            cc = Cosmology(lmax=int(kellmax),pickling=True)
            theory = cc.theory
            bin_edges = np.arange(kellmin,kellmax,dell)
            myNls = NlGenerator(lmap,theory,bin_edges,gradCut=gradCut)
            nTX,nPX,nTY,nPY = myNls.updateNoiseAdvanced(beamTX,noiseTX,beamPX,noisePX,tellminX,tellmaxX,pellminX,pellmaxX,beamTY,noiseTY,beamPY,noisePY,tellminY,tellmaxY,pellminY,pellmaxY,(lkneeTX,lkneePX),(alphaTX,alphaPX),(lkneeTY,lkneePY),(alphaTY,alphaPY),None,None,None,None,None,None,None,None,fgFuncX,fgFuncY,None,None,None,None,None,None,None,None)


            ls,Nls,ells,dclbb,efficiency = myNls.getNlIterative(pols,kellmin,kellmax,tellmax,pellmin,pellmax,dell=dell,halo=True)

            ls = ls[1:-1]
            Nls = Nls[1:-1]


            from scipy.interpolate import interp1d

            from orphics.io import Plotter
            ellkk = np.arange(2,9000,1)
            Clkk = theory.gCl("kk",ellkk)    
            #pl = Plotter(scaleY='log',scaleX='log')
            #pl.add(ellkk,4.*Clkk/2./np.pi)


            # from orphics.tools.stats import bin1D
            # dls = np.diff(ls)[0]
            # bin_edges_nls = np.arange(ls[0]-dls/2.,ls[-1]+dls*3./2.,dls)

            # print ls
            # print dls
            # print bin_edges_nls
            # print bin_edges

            # binner1d = bin1D(bin_edges_nls)
            # ellcls , clkk_binned = binner1d.binned(ellkk,Clkk)

            clfunc = interp1d(ellkk,Clkk,bounds_error=False,fill_value="extrapolate")
            clkk_binned = clfunc(ls)

            #pl.add(ls,4.*clkk_binned/2./np.pi,ls="none",marker="x")
            #pl.add(ls,4.*Nls/2./np.pi,ls="--")
            np.savetxt(bigDataDir+"nlsave_"+expName+"_"+lensName+".txt",np.vstack((ls,Nls)).transpose())

            Nls += clkk_binned
        np.savetxt(bigDataDir+"nlsaveTot_"+expName+"_"+lensName+"_v3_"+str(v3mode)+".txt",np.vstack((ls,Nls)).transpose())
        
        #pl.add(ls,4.*Nls/2./np.pi,ls="-.")
        #pl.legendOn(loc='lower left',labsize=10)
        #pl.done("output/Nl_"+expName+lensName+".png")
        #ls,Nls = np.loadtxt("data/LA_pol_Nl.txt",unpack=True,delimiter=",")
        # print ls,Nls
    else:
        ls = None
        Nls = None
        #beamY = None
        #miscentering = None
        #doRayDeriv = False
        rayFid = None
        rayStep = None
    
    clttfile = Config.get('general','clttfile')


    if doSZ:
        clusterDict = dict_from_section(Config,'cluster_params')

        cc = ClusterCosmology(fparams,constDict,clTTFixFile=clttfile)
        if doSZ:
            HMF = Halo_MF(cc,mgrid,zgrid)
            kh = HMF.kh
            pk = HMF.pk

    else:
        clusterDict = None
        kh = None
        pk = None
        doFg = None
        

else:
    #doRayDeriv = None
    pzcut = None
    rayFid = None
    rayStep = None
    doLens = None
    doSZ = None
    #beamY = None
    #miscentering = None
    mgrid = None
    zgrid = None
    ls = None
    Nls = None
    fparams = None
    constDict = None
    clttfile = None
    clusterDict = None
    beam = None
    noise = None
    fsky = None
    freq = None
    lkneeT = None
    alphaT = None
    kh = None
    pk = None
    Mexp_edges = None
    z_edges = None
    doFg = None
    dotsz_cib = None
    v3mode = None

if rank==0: print("Broadcasting...")
#doRayDeriv = comm.bcast(doRayDeriv, root = 0)
doFg = comm.bcast(doFg, root = 0)
dotsz_cib = comm.bcast(dotsz_cib, root = 0)
pzcut = comm.bcast(pzcut, root = 0)
rayFid = comm.bcast(rayFid, root = 0)
rayStep = comm.bcast(rayStep, root = 0)
doLens = comm.bcast(doLens, root = 0)
doSZ = comm.bcast(doSZ, root = 0)
#beamY = comm.bcast(beamY, root = 0)
#miscentering = comm.bcast(miscentering, root = 0)
mgrid = comm.bcast(mgrid, root = 0)
zgrid = comm.bcast(zgrid, root = 0)
ls = comm.bcast(ls, root = 0)
Nls = comm.bcast(Nls, root = 0)
fparams = comm.bcast(fparams, root = 0)
constDict = comm.bcast(constDict, root = 0)
clttfile = comm.bcast(clttfile, root = 0)
clusterDict = comm.bcast(clusterDict, root = 0)
beam = comm.bcast(beam, root = 0)
noise = comm.bcast(noise, root = 0)
fsky = comm.bcast(fsky, root = 0)
v3mode = comm.bcast(v3mode, root = 0)
freq = comm.bcast(freq, root = 0)
lkneeT = comm.bcast(lkneeT, root = 0)
alphaT = comm.bcast(alphaT, root = 0)
kh = comm.bcast(kh, root = 0)
pk = comm.bcast(pk, root = 0)
Mexp_edges = comm.bcast(Mexp_edges, root = 0)
z_edges = comm.bcast(z_edges, root = 0)
if rank==0: print("Broadcasted.")


cc = ClusterCosmology(fparams,constDict,clTTFixFile=clttfile)
if doSZ:
    HMF = Halo_MF(cc,mgrid,zgrid,kh=kh,powerZK=pk)
    SZCluster = SZ_Cluster_Model(cc,clusterDict,rms_noises = noise,fwhms=beam,freqs=freq,lknee=lkneeT,alpha=alphaT,fg=doFg,tsz_cib=dotsz_cib,v3mode=v3mode,fsky=fsky)

numms = mgrid.size
numzs = zgrid.size
if doLens:
    MerrGrid = np.zeros((numms,numzs))
    if True: #doRayDeriv:
        MerrGridUp = np.zeros((numms,numzs))
        MerrGridDn = np.zeros((numms,numzs))
        
if doSZ: siggrid = np.zeros((numms,numzs))
numes = numms*numzs



indices = np.arange(numes)
splits = np.array_split(indices,numcores)

if rank==0:
    lengths = [len(split) for split in splits]
    mintasks = min(lengths)
    maxtasks = max(lengths)
    print("I have ",numcores, " cores to work with.")
    print("And I have ", numes, " tasks to do.")
    print("Each worker gets at least ", mintasks, " tasks and at most ", maxtasks, " tasks.")
    zfrac = float(len(z_edges[np.where(z_edges>pzcut)]))/len(z_edges)
    #zfrac = old_div(float(len(z_edges[np.where( check_pzcut_less(z_edges, pzcut) )])),len(z_edges))
    buestguess = (0.5*int(doSZ)+((1.+(2.*zfrac))*5.0*int(doLens)))*maxtasks
    print("My best guess is that this will take ", buestguess, " seconds.")
    print("Starting the slow part...")


mySplitIndex = rank

mySplit = splits[mySplitIndex]

if doLens: 
    #import pixell.fft as fftfast
    import enlib.fft as fftfast
    arcStamp = 100.
    pxStamp = 0.05
    Npix = int(old_div(arcStamp,pxStamp))
    B = fftfast.fft(np.zeros((Npix,Npix)),axes=[-2,-1],flags=['FFTW_MEASURE'])
# Ndown = fftfast.fft_len(Npix,direction="below")
# Nup = fftfast.fft_len(Npix,direction="above")
# print Npix,Ndown,Nup

for index in mySplit:
            
    mindex,zindex = np.unravel_index(index,(numms,numzs))
    mass = mgrid[mindex]
    z = zgrid[zindex]

    if doLens:
        kmax = 8000
        overdensity = 500
        critical = True
        atClusterZ = True
        concentration = cc.Mdel_to_cdel(mass,z,overdensity) #1.18
        # if miscentering:
        #     ray = beamY/2.
        # else:
        #     ray = None
        if check_pzcut_less(z, pzcut):
            ray = rayFid
        else:
            ray = None
        
        snRet,k500,std = NFWMatchedFilterSN(cc,mass,concentration,z,ells=ls,Nls=Nls,kellmax=kmax,overdensity=overdensity,critical=critical,atClusterZ=atClusterZ,saveId=None,rayleighSigmaArcmin=ray,arcStamp=arcStamp,pxStamp=pxStamp)
        MerrGrid[mindex,zindex] = old_div(1.,snRet)
        if True: #doRayDeriv:
            rayUp = rayFid+old_div(rayStep,2.)
            if check_pzcut_less(z, pzcut):
                snRetUp,k500Up,stdUp = NFWMatchedFilterSN(cc,mass,concentration,z,ells=ls,Nls=Nls,kellmax=kmax,overdensity=overdensity,critical=critical,atClusterZ=atClusterZ,saveId=None,rayleighSigmaArcmin=rayUp,arcStamp=arcStamp,pxStamp=pxStamp)
            else:
                snRetUp = snRet
            MerrGridUp[mindex,zindex] = old_div(1.,snRetUp)
            rayDn = rayFid-old_div(rayStep,2.)
            if check_pzcut_less(z, pzcut):
                snRetDn,k500Dn,stdDn = NFWMatchedFilterSN(cc,mass,concentration,z,ells=ls,Nls=Nls,kellmax=kmax,overdensity=overdensity,critical=critical,atClusterZ=atClusterZ,saveId=None,rayleighSigmaArcmin=rayDn,arcStamp=arcStamp,pxStamp=pxStamp)
            else:
                snRetDn = snRet
            MerrGridDn[mindex,zindex] = old_div(1.,snRetDn)

        
    if doSZ:
        var = SZCluster.quickVar(10**mass,z)
        siggrid[mindex,zindex] = np.sqrt(var)




if rank!=0:
    if doLens:
        MerrGrid = MerrGrid.astype(np.float64)
        comm.Send(MerrGrid, dest=0, tag=77)
        if True:#doRayDeriv:
            MerrGridUp = MerrGridUp.astype(np.float64)
            MerrGridDn = MerrGridDn.astype(np.float64)
            comm.Send(MerrGridUp, dest=0, tag=98)
            comm.Send(MerrGridDn, dest=0, tag=99)
            
    if doSZ:
        siggrid = siggrid.astype(np.float64)
        comm.Send(siggrid, dest=0, tag=78)
    
else:
    print("Waiting for workers...")

    import pickle as pickle

    if doLens:
        for i in range(1,numcores):
            print("Waiting for lens ", i ," / ", numcores)
            data = np.zeros(MerrGrid.shape, dtype=np.float64)
            comm.Recv(data, source=i, tag=77)
            MerrGrid += data.copy()
            if True:#doRayDeriv:
                data = np.zeros(MerrGridUp.shape, dtype=np.float64)
                comm.Recv(data, source=i, tag=98)
                MerrGridUp += data.copy()
                data = np.zeros(MerrGridDn.shape, dtype=np.float64)
                comm.Recv(data, source=i, tag=99)
                MerrGridDn += data.copy()
                

        pickle.dump((Mexp_edges,z_edges,MerrGrid),open(sfisher.mass_grid_name_cmb(bigDataDir,expName,gridName,lensName,version+suffix),'wb'))
        pickle.dump((Mexp_edges,z_edges,MerrGridUp),open(sfisher.mass_grid_name_cmb_up(bigDataDir,expName,gridName,lensName,version+suffix),'wb'))
        pickle.dump((Mexp_edges,z_edges,MerrGridDn),open(sfisher.mass_grid_name_cmb_dn(bigDataDir,expName,gridName,lensName,version+suffix),'wb'))
        
    if doSZ:
        for i in range(1,numcores):
            print("Waiting for sz ", i," / ", numcores)
            data = np.zeros(siggrid.shape, dtype=np.float64)
            comm.Recv(data, source=i, tag=78)
            siggrid += data.copy()


        pickle.dump((Mexp_edges,z_edges,siggrid),open(bigDataDir+"szgrid_"+expName+"_"+gridName+ "_v" + version+suffix+".pkl",'wb'))
