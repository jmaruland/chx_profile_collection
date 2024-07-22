import asyncio
import time
from ophyd import EpicsMotor
from epics import caput
from epics import caget
from math import radians
from IPython.core.magic import Magics, magics_class, line_magic
from bluesky import RunEngine
from bluesky.utils import ProgressBarManager
from bluesky.plan_stubs import rd
from matplotlib import cm

def set_bpm(gain='1uA'):
    """
    temporary fix to modify gains for Sydor DBPM
    set_bpm('1uA') available gains: [1uA, 10uA]
    """
    cal_pv='XF:11IDB-BI{XBPM:02}Cal:'
    gain_dict={
    '1uA':{'gain_level':0,'AOffset-SP':-774,'BOffset-SP':-1294,'COffset-SP':-1094,'DOffset-SP':-1764,'AGain-SP':44013,'BGain-SP':29800,'CGain-SP':31155,'DGain-SP':56293},
    '10uA':{'gain_level':1,'AOffset-SP':-702,'BOffset-SP':-1237,'COffset-SP':-1042,'DOffset-SP':-1697,'AGain-SP':322938,'BGain-SP':311398,'CGain-SP':267000,'DGain-SP':354306},
    }
    caput('XF:11IDB-BI{XBPM:02}Gain:Level-SP',gain_dict[gain]['gain_level'])
    print('changed Gain Stage, waiting 10s for auto-settings to complete before overwriting them....')
    RE(sleep(10))
    g=list(gain_dict[gain].keys())
    g.remove('gain_level')    
    for i in g:
        caput(cal_pv+i,gain_dict[gain][i])
    RE(sleep(2))
    check=True
    for i in g:
        check=check*caget(cal_pv+i)==gain_dict[gain][i]
    if check:
        print('offsets and gains successfully set!')
    else:
        print('failed to set offsets and gains correctly :-(')

def md_reset(  ):
    sid = RE.md['scan_id']
    RE.md.update({'beamline_id': 'CHX', 'scan_id': sid, 'user': 'CHX', 'run': '2018-3', 'owner': 'CHX', 'sample': 'N.A.'})
    

def get_beam_center_update( uid = -1, threshold = 200  ):
    '''Find the beam center on detector and update the PV accordingly
       The image is masked by pixel mask and the known pixel masks
    Input:
        uid: string or integer, e.g, -1 is the last data
        threshold: the max intensity on the detector, if less, will not update beam center
    Output:
        None
    
    '''
    hdr = db[uid]
    keys = [k for k, v in hdr.descriptors[0]['data_keys'].items()     if 'external' in v]
    det = keys[0]    
    print('The detector is %s.'%det)
    imgs = list(db[uid].data(det))[0]
    if det =='eiger1m_single_image':
        Chip_Mask=np.load( '/XF11ID/analysis/2017_1/masks/Eiger1M_Chip_Mask.npy')
        img = imgs[0]
    elif det =='eiger4m_single_image' or det == 'image':    
        Chip_Mask= np.array(np.load( '/XF11ID/analysis/2017_1/masks/Eiger4M_chip_mask.npy'), dtype=bool)
        BadPix =     np.load('/XF11ID/analysis/2018_1/BadPix_4M.npy'  )  
        Chip_Mask.ravel()[BadPix] = 0
        Chip_Mask[1225:1234, 1156:1163] = 0
        img = imgs[0]
        pixel_mask =  1- np.int_( np.array( imgs.md['pixel_mask'], dtype= bool)  )
    elif det =='eiger500K_single_image':
        #print('here')
        Chip_Mask=  np.load( '/XF11ID/analysis/2017_1/masks/Eiger500K_Chip_Mask.npy')  #to be defined the chip mask
        Chip_Mask = np.rot90(Chip_Mask)
        pixel_mask = np.rot90(  1- np.int_( np.array( imgs.md['pixel_mask'], dtype= bool))   )
        img = np.rot90( imgs[0] )
    else:
        Chip_Mask = 1   
     
    img = img * pixel_mask * Chip_Mask
    imax = np.max(img)
    print('The value of the max intensity is: %s.'%imax)
    if imax > threshold:
        cx_, cy_ = np.where( img == np.max(img) )  
        
        if det =='eiger4m_single_image':    
            cx, cy =cy_[0], cx_[0]
            caput('XF:11IDB-ES{Det:Eig4M}cam1:BeamX',  cx)
            caput('XF:11IDB-ES{Det:Eig4M}cam1:BeamY',  cy)
            
             
        elif det =='eiger500K_single_image':    
            cx, cy =cx_[0], cy_[0]
            cx = 1030 -1 - cx
            caput('XF:11IDB-ES{Det:Eig500K}cam1:BeamX',  cx)
            caput('XF:11IDB-ES{Det:Eig500K}cam1:BeamY',  cy)
            
        elif det =='eiger1m_single_image':   
            cx, cy =cy_[0], cx_[0] 
            caput('XF:11IDB-ES{Det:Eig1m}cam1:BeamX',  cx)
            caput('XF:11IDB-ES{Det:Eig1m}cam1:BeamY',  cy)
        else:
            pass
        print('The direct beam center is changed to (%s, %s)'%(cx, cy ) ) 
        center = [ cx, cy ]            
        print( 'The center is: %s.'%center)#, cx, cy)    
    else:
        print('The scattering intensity is too low. Can not find the beam center. Please check your beamline.')
    show_img( img,  vmin= 1e-3, vmax= 1e1, logs=True, aspect=1, cmap = cm.winter ,center= center)#[::-1] )#save_format='tif',
             #image_name= 'uid=%s'%uid,  #cmap = cmap_albula,
             #save=False,     path='', center= center[::-1] )

 



def Update_direct_bc( detxy=[134.9713, -132.6926], saxs_theta=0.0, bc = [ 1131, 1229],  det = '4m' ):
    '''Update direct beam center 
    Record detector position to metadata
    If the detector is changed (different from the previous value), will change the meta data of direct beam center
    Parameters:
    	det: string, 4m for eiger 4M
    		     1m for eiger 1M
    		     500k for eiger 500K    
    '''
    detector_distance = caget("XF:11IDB-ES{Det:Eig4M}cam1:DetDist")
    dx = (yield from rd(bps.saxs_detector.x.user_readback))
    dy = (yield from rd(saxs_detector.y.user_readback))
    current_theta = caget("XF:11IDB-ES{Tbl:SAXS-Ax:Theta}Mtr.RBV")
    angle_shift = (current_theta-saxs_theta)*np.pi/180.0*(detector_distance*1000.0)
    dx = dx+angle_shift

    if det =='4m':
        nbx = int( bc[0] + (dx-detxy[0])*1000/75.) 
        nby = int( bc[1] + (dy-detxy[1])*1000/75.)

        caput('XF:11IDB-ES{Det:Eig4M}cam1:BeamX',  nbx)
        caput('XF:11IDB-ES{Det:Eig4M}cam1:BeamY',  nby)
        print('The direct beam center is changed to (%s, %s)'%(nbx, nby ) )
        
        

    


def beam_on():
    # foil_x.move(-22.0)
    #yield from mv(foil_x, -18.5)
    print('use att2.set_T(1) instead')

def beam_off():
    # foil_x.move(-21.0)
    #yield from mv(foil_x, -21)
    print('use att2.set_T(0) instead')


@magics_class
class CHXMagics(Magics):
    RE = RunEngine({}, loop = asyncio.new_event_loop())
    RE.waiting_hook = ProgressBarManager()

    def _ensure_idle(self):
        if self.RE.state != 'idle':
            print('The RunEngine invoked by magics cannot be resumed.')
            print('Aborting...')
            self.RE.abort()

    @line_magic
    def beam_on(self, line):
        plan = beam_on()
        self.RE(plan)
        self._ensure_idle()

    @line_magic
    def beam_off(self, line):
        plan = att2.set_T(0)
        self.RE(plan)
        self._ensure_idle()

get_ipython().register_magics(CHXMagics)


def change_motor_name( device):
    for k in device.component_names:
        if hasattr( getattr(device, k), 'user_readback'):
            getattr(device, k).user_readback.name = getattr(device, k).name
        elif hasattr( getattr(device, k), 'readback'):
            getattr(device, k).readback.name = getattr(device, k).name


for motors in [diff, bpm2, mbs, dcm, tran, s1, s2, s4]:
    change_motor_name( motors )

    

    
    

def ct_500k(expt=.0001,frame_rate=9000,imnum=1,comment='eiger500K image'):
    caput('XF:11IDB-ES{Det:Eig500K}cam1:FWClear',1)   #remove files from detector
    caput('XF:11IDB-ES{Det:Eig500K}cam1:ArrayCounter',0)
    eiger500k_single.photon_energy.put(9652.0)
    #add some metadata:
    RE.md['transmission']=att.get_T()
    #RE.md['T_yoke']=str(caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I'))
    eiger500k_single.cam.num_images.put(imnum)
    eiger500k_single.cam.acquire_time.put(expt)
    eiger500k_single.cam.acquire_period.put(max([0.000112,1./frame_rate]))
    RE(count([eiger500k_single]),Measurement=comment)
    #remove meta data keys
    a=RE.md.pop('transmission')
    #a=RE.md.pop('T_yoke')

hdm_feedback_selector = EpicsSignal('XF:11IDA-OP{Mir:HDM-Ax:P}Sts:FB-Sel',
                                    name='hdm_feedback_selector')
bpm2_feedback_selector_b = EpicsSignal('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP', name='bpm2_feeedback_selector_b')
bpm2_feedback_selector_a = EpicsSignal('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP', name='bpm2_feeedback_selector_a')


#class BPMReadings(Device):
#    x = Cpt(EpicsSignal, 'XF:11IDB-BI{XBPM:02}Pos:X-I')
#   y = Cpt(EpicsSignal, 'XF:11IDB-BI{XBPM:02}Pos:Y-I')
#
#bpm_readings = BPMReadings('', name='bpm_readings')

def feedback_ON(tolerance=1.0):
    '''
    turns Epics feedback (HDM) OFF and DBPM feedback ON; 
    Note: shutter(s) must be opened and sample should be protected
    '''
    #mov(foil_x, 8)
    #yield from beam_off()  #using monitor holder to protect the sample
    #fast_sh.open()
    #yield from bp.sleep(2)
    #att.set_T(1)
    
    yield from bps.sleep(2)  #just in case e.g. the shutter is still opening ...
    yield from mv(hdm_feedback_selector, 0) # turn off epics pid feedback on HDM encoder    
    yield from mv(bpm2_feedback_selector_b, 1)
    yield from bps.sleep(2)
    yield from mv(bpm2_feedback_selector_a, 1)
    yield from bps.sleep(2)
    # Check that the beam positions in x and y are within some tolerance of 0
    TOLERANCE = tolerance
    #reading = yield from bp.read(bpm_readings)
    #y_pos = reading['bpm_readings_y']['value']a
    y_pos = caget('XF:11IDB-BI{XBPM:02}Pos:Y-I')
    if abs(y_pos) > TOLERANCE:
        # cycle it
        yield from mv(bpm2_feedback_selector_b, 0)
        yield from bps.sleep(1)
        yield from mv(bpm2_feedback_selector_b, 1)
    #reading = yield from bp.read(bpm_readings)
    #x_pos = reading['bpm_readings_x']['value']
    x_pos = caget('XF:11IDB-BI{XBPM:02}Pos:X-I')
    if abs(x_pos) > TOLERANCE:
        yield from mv(bpm2_feedback_selector_a, 0)
        yield from bps.sleep(1)
        yield from mv(bpm2_feedback_selector_a, 1)

hdm_pitch = EpicsSignal('XF:11IDA-OP{Mir:HDM-Ax:P}Pos-I', name='hdm_pitch')
hdm_pid_setpoint = EpicsSignal('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP', name='hdm_pid_setpoint')

def feedback_OFF(epics_feedback_on=True): 
    """
    feedback_OFF(epics_feedback_on=True)
    Turns the beam position DBPM feedback OFF and, if epics_feedback_on=True (default) 
    turns EPICS (HDM encoder) feedback ON.
    """
    # Where are we now?
    reading = yield from bp.read(hdm_pitch)
    # 'reading' looks like
    # {'hdm_pitch': {'value': -1869.0720000000001, 'timestamp': 1504122664.521454}}
    # so we unpack the value from it...
    pos = reading['hdm_pitch']['value']
    #DBPM feedback OFF:
    yield from mv(bpm2_feedback_selector_b, 0)
    yield from mv(bpm2_feedback_selector_a, 0)
    # EPICS feedback ON:
    if epics_feedback_on: 
       yield from mv(hdm_pid_setpoint, pos)
       #Set the PID loop to maintain this position.
       yield from mv(hdm_feedback_selector, 1)


def snap(det='eiger4m',expt=0.1,comment='Single image'):
    """
    sets exp time (and period) to expt (default 0.1s)
    sets #images and #triggers both to 1
    takes an Eiger image
    """
    if det == 'eiger4m':
        dets=[eiger4m_single]
        caput('XF:11IDB-ES{Det:Eig4M}cam1:NumImages',1)
        caput('XF:11IDB-ES{Det:Eig4M}cam1:NumTriggers',1)
        caput('XF:11IDB-ES{Det:Eig4M}cam1:AcquireTime',expt)
        caput('XF:11IDB-ES{Det:Eig4M}cam1:AcquirePeriod',expt)
        RE(count(dets),Measurement=comment)
    elif det == 'eiger1m':
        dets=[eiger1m_single]
        caput('XF:11IDB-ES{Det:Eig1M}cam1:NumImages',1)
        caput('XF:11IDB-ES{Det:Eig1M}cam1:NumTriggers',1)
        caput('XF:11IDB-ES{Det:Eig1M}cam1:AcquireTime',expt)
        caput('XF:11IDB-ES{Det:Eig1M}cam1:AcquirePeriod',expt)
        RE(count(dets),Measurement=comment)
    elif det == 'eiger500k':
        dets=[eiger500k_single]
        caput('XF:11IDB-ES{Det:Eig500K}cam1:NumImages',1)
        caput('XF:11IDB-ES{Det:Eig500K}cam1:NumTriggers',1)
        caput('XF:11IDB-ES{Det:Eig500K}cam1:AcquireTime',expt)
        caput('XF:11IDB-ES{Det:Eig500K}cam1:AcquirePeriod',expt)
        RE(count(dets),Measurement=comment)


###### sample-detector distance macros for SAXS ##########

def tube_length(tube_nr):
    '''
    function to get tube length of SAXS instrument, from label on tube
    calling sequence: tube_length(tube_nr) -> returns tube length in mm
    tube_nr: see label on instrument. This is only the length of the tube, NOT the sample-detector distance!
    '''
    tube_l=np.array([1758.24,2764.78,3766.66,4616.18,6789.28,9790.93,12792.57,15742.99])-228.22
    if tube_nr >= 0 and tube_nr <=7:
        return tube_l[tube_nr]
    else: raise param_Exception('error: argument tube_nr must be between 0 and 7')
    

def get_saxs_sd(tube_nr,detector='eiger4m'):
    '''
    function returns sample detector distance for SAXS instrument
    based on tube nr, detector and Z1 position
    calling sequence: get_saxs_sd(tube_nr,detector='eiger4m') -> returns sample-detector distance [mm]
    detector: 'eiger4m','backplate' ('backplate': distance to the plate with the viewports in it)
    '''
    tube=tube_length(tube_nr)
    if detector == 'eiger4m':
        det_chamber=247.136
    elif detector == 'backplate':
        det_chamber = 769.536
    else: raise param_Exception('error: detector '+detector+'currently not defined...')
    sd=273.62+caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z1}Mtr.RBV')+tube+det_chamber
    print('sample-detector distance using tube_nr: '+str(tube_nr)+' detector: '+detector+' at Z1 position '+str(caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z1}Mtr.RBV'))+': '+str(sd)+'mm')
    return sd

def calc_saxs_sd(tube_nr,z1,detector='eiger4m'):
    '''
    function calculates sample detector distance for SAXS instrument
    based on tube nr, detector and Z1 position
    calling sequence: calc_saxs_sd(tube_nr,z1,detector='eiger4m') -> returns sample detector distance [mm]
	detector: 'eiger4m','backplate' ('backplate': distance to the plate with the viewports in it)
    '''
    tube=tube_length(tube_nr)
    if detector == 'eiger4m':
        det_chamber=247.136
    elif detector == 'backplate':
        det_chamber = 769.536
    else: raise param_Exception('error: detector '+detector+'currently not defined...')
    sd=273.62+z1+tube+det_chamber
    print('sample-detector distance using tube_nr: '+str(tube_nr)+' detector: '+detector+' at Z1 position '+str(z1)+': '+str(sd)+'mm')
    return sd

def update_saxs_sd(tube_nr,detector='eiger4m/eiger500k'):
    '''
    get sample detector distance for SAXS instrument
    based on tube nr, detector and Z1 position and update metadata
    calling sequence: update_saxs_sd(tube_nr,detector='eiger4m/eiger500k')
    '''
    sd=get_saxs_sd(tube_nr,detector='eiger4m')
    if detector == 'eiger4m/eiger500k':
        print('updating metadata in Eiger4M HDF5 file...')
        caput('XF:11IDB-ES{Det:Eig4M}cam1:DetDist',sd/1000.)
        print('updating metadata in Eiger500k HDF5 file...')
        caput('XF:11IDB-ES{Det:Eig500K}cam1:DetDist',(sd+29.9)/1000.)
    else: raise param_Exception('error: detector '+detector+'currently not defined...')
    

class param_Exception(Exception):
    pass 

########## END sample-detector distance macros for SAXS ####################

# temporary fix for not having the fast shutter
def eiger4m_series(expt=.1,acqp='auto',imnum=5,comment=''):
    """
    July 2017: fast shutter broken, use edge of empty slot in monitor chamber
    use 'manual' triggering of eiger4m (implemented by Dan)
    """
    print('start of series: '+time.ctime())
    if acqp=='auto':
        acqp=expt
        #print('setting acquire period to '+str(acqp)+'s')
    if expt <.00134:
            expt=.00134
    else:
            pass
    seqid=caget('XF:11IDB-ES{Det:Eig4M}cam1:SequenceId')+1
    idpath=caget('XF:11IDB-ES{Det:Eig4M}cam1:FilePath',' {"longString":true}')
    caput('XF:11IDB-ES{Det:Eig4M}cam1:FWClear',1)    #remove files from the detector DISABLE FOR MANUAL DOWNLOAD!!!
    caput('XF:11IDB-ES{Det:Eig4M}cam1:ArrayCounter',0) # set image counter to '0'
    if imnum < 500:                                                            # set chunk size
            caput('XF:11IDB-ES{Det:Eig4M}cam1:FWNImagesPerFile',10)
    else: 
            caput('XF:11IDB-ES{Det:Eig4M}cam1:FWNImagesPerFile',100)        
    detector=eiger4m_single
    detector.cam.acquire_time.value=expt       # setting up exposure for eiger1m/4m_single
    detector.cam.acquire_period.value=acqp
    detector.cam.num_images.value=imnum
    detector.num_triggers.put(1)
    #print('adding metadata: '+time.ctime())
    RE(sleep(2)) # needed to ensure values are updated in EPICS prior to reading them back...
    RE.md['exposure time']=str(expt)        # add metadata information about this run
    #print('adding metadata acquire period: '+str(detector.cam.acquire_period.value))
    RE.md['acquire period']=str(acqp)
    RE.md['shutter mode']='single using edge in monitor chamber'
    RE.md['number of images']=str(imnum)
    RE.md['data path']=idpath
    RE.md['sequence id']=str(seqid)
    RE.md['transmission']=att.get_T()
    RE.md['diff_yh']=str(round(diff.yh.user_readback.get(), 4))
    ## add experiment specific metadata:
    #RE.md['T_yoke']=str(caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I'))
    #RE.md['T_sample']=str(caget('XF:11IDB-ES{Env:01-Chan:D}T:C-I'))
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 1:
        RE.md['feedback_x']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 0:
        RE.md['feedback_x']='off'
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 1:
        RE.md['feedback_y']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 0:
        RE.md['feedback_y']='off'
    ## end experiment specific metadata
    ## would be nice to make the olog entry here, but how do we get the uid at this stage?
    print('taking data series: exposure time: '+str(expt)+'s,  period: '+str(acqp)+'s '+str(imnum)+'frames')
    print('Dectris sequence id: '+str(int(seqid)))
    ### data acquisition
    RE(manual_count(det=eiger4m_single),Measurement=comment)
    beam_on()
    RE.resume()
    beam_off()
    ### end data acquisition
    a=RE.md.pop('exposure time')        # remove eiger series specific meta data (need better way to remove keys 'silently'....)
    a=RE.md.pop('acquire period')
    #a=RE.md.pop('shutter mode')
    a=RE.md.pop('number of images')
    a=RE.md.pop('data path')
    a=RE.md.pop('sequence id')
    a=RE.md.pop('diff_yh')
    ## remove experiment specific dictionary key
    #a=RE.md.pop('T_yoke')
    #a=RE.md.pop('T_sample')
    a=RE.md.pop('feedback_x')
    a=RE.md.pop('feedback_y')
    a=RE.md.pop('transmission')
    log_manual_count()

# temporary fix for not having the fast shutter
def eiger1m_series(expt=.1,acqp='auto',imnum=5,comment=''):
    """
    July 2017: fast shutter broken, use edge of empty slot in monitor chamber
    use 'manual' triggering of eiger1m (implemented by Dan)
    """
    print('start of series: '+time.ctime())
    if acqp=='auto':
        acqp=expt
        #print('setting acquire period to '+str(acqp)+'s')
    if expt <.00033334:
            expt=.00033334
    else:
            pass
    seqid=caget('XF:11IDB-ES{Det:Eig1M}cam1:SequenceId')+1
    idpath=caget('XF:11IDB-ES{Det:Eig1M}cam1:FilePath',' {"longString":true}')
    caput('XF:11IDB-ES{Det:Eig1M}cam1:FWClear',1)    #remove files from the detector DISABLE FOR MANUAL DOWNLOAD!!!
    caput('XF:11IDB-ES{Det:Eig1M}cam1:ArrayCounter',0) # set image counter to '0'
    if imnum < 500:                                                            # set chunk size
            caput('XF:11IDB-ES{Det:Eig1M}cam1:FWNImagesPerFile',10)
    else: 
            caput('XF:11IDB-ES{Det:Eig1M}cam1:FWNImagesPerFile',100)        
    detector=eiger1m_single
    detector.cam.acquire_time.value=expt       # setting up exposure for eiger1m/4m_single
    detector.cam.acquire_period.value=acqp
    detector.cam.num_images.value=imnum
    detector.num_triggers.put(1)
    #print('adding metadata: '+time.ctime())
    RE(sleep(2)) # needed to ensure values are updated in EPICS prior to reading them back...
    RE.md['exposure time']=str(expt)        # add metadata information about this run
    #print('adding metadata acquire period: '+str(detector.cam.acquire_period.value))
    RE.md['acquire period']=str(acqp)
    RE.md['shutter mode']='single using edge in monitor chamber'
    RE.md['number of images']=str(imnum)
    RE.md['data path']=idpath
    RE.md['sequence id']=str(seqid)
    RE.md['transmission']=att.get_T()*att2.get_T()
    ## add experiment specific metadata:
    RE.md['T_yoke']=str(caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I'))
    #RE.md['T_sample']=str(caget('XF:11IDB-ES{Env:01-Chan:D}T:C-I'))
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 1:
        RE.md['feedback_x']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 0:
        RE.md['feedback_x']='off'
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 1:
        RE.md['feedback_y']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 0:
        RE.md['feedback_y']='off'
    ## end experiment specific metadata
    ## would be nice to make the olog entry here, but how do we get the uid at this stage?
    print('taking data series: exposure time: '+str(expt)+'s,  period: '+str(acqp)+'s '+str(imnum)+'frames')
    print('Dectris sequence id: '+str(int(seqid)))
    ### data acquisition
    RE(manual_count(det=eiger1m_single),Measurement=comment)
    #beam_on()
    RE.resume()
    #beam_off()
    ### end data acquisition
    a=RE.md.pop('exposure time')        # remove eiger series specific meta data (need better way to remove keys 'silently'....)
    a=RE.md.pop('acquire period')
    #a=RE.md.pop('shutter mode')
    a=RE.md.pop('number of images')
    a=RE.md.pop('data path')
    a=RE.md.pop('sequence id')
    ## remove experiment specific dictionary key
    a=RE.md.pop('T_yoke')
    #a=RE.md.pop('T_sample')
    a=RE.md.pop('feedback_x')
    a=RE.md.pop('feedback_y')
    a=RE.md.pop('transmission')
    log_manual_count()


def prep_series_feedback():
    fast_sh.open()
    yield from bps.sleep(.1)
    #RE(mv(hdm_feedback_selector, 0)) # turn off epics pid feedback on HDM encoder    
    #caput('XF:11IDA-OP{Mir:HDM-Ax:P}Sts:FB-Sel',0)  # swapped: switch off encoder feedback after starting feedback on the BPM
    caput('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP',1)
    caput('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP',1)
    yield from bps.sleep(.1)
    caput('XF:11IDA-OP{Mir:HDM-Ax:P}Sts:FB-Sel',0)
    yield from bps.sleep(.25)
    #RE(mv(bpm2_feedback_selector_a, 1))
    
def trigger_ready():
    #caput('XF:11ID-CT{M1}bi3',1) # for printer
    caput('XF:11ID-CT{ES:1}bi2',1) # fake for beamline

    
def wait_for_pv(dets, ready_signal,feedback_on=False ,md=None):
    if md is None:
        md = {}
    def still_waiting():
        return ready_signal.get() != 1
    def wait_for_motor_to_cross_threshold():
        return motor.postion < threshold
    @bpp.stage_decorator(dets)
    @bpp.run_decorator(md=md)
    def inner():
        print('waiting for trigger signal (PV)...')
        trigger_ready() # let the world know: ready to be triggered
        while still_waiting():
            yield from bps.sleep(.01)
        # if feedback_on:
        #     yield from prep_series_feedback() # LW 03/2024: no longer needed, feedback is always on
        yield from bps.trigger_and_read(dets)        
    yield from inner()
    
    
    
    
    

def wait_for_motor(dets, motor, target, threshold, start_move=False, md=None): 
     if md is None: 
         md = {} 
          
     def still_waiting(): 
         p = motor.position 
         #print(np.abs(p-target)<threshold) 
         return np.abs(p-target) > threshold 
  
     @bpp.stage_decorator(dets) 
     @bpp.run_decorator(md=md)
     def inner():
         print('waiting for %s to reach %s within threshold of %s'%(motor.name,target,threshold))
         if start_move:
             yield from bps.abs_set(motor, target, feedback_on= False, group='the_motor') 
         while still_waiting(): 
             yield from bps.sleep(.1)
         #if feedback_on:
         #   yield from prep_series_feedback() 
         yield from bps.trigger_and_read(dets) 
         yield from bps.wait(group='the_motor') 
     yield from inner() 


def update_beam_position_dict(detector):
    """
    update_beam_position_dict(detector) -> detector ='eiger4m' or 'eiger500k'
    run after updating direct beam position in CSS (after measuring direct beam position) to enable automatic tracking of direct beam position
    updates RE.md['beam_position_dict']
    re-create if RE.md['beam_position_dict'] got deleted:
    RE.md['beam_position_dict']={'eiger4m': {'beam_center_x': 1126.0, 'beam_center_y': 1209.0,'det_x': 120.20935000000001,'det_y': -134.52025},
   'eiger500k': {'beam_center_x': 200,'beam_center_y': 230,'det_x': 23.45,'det_y': 56.0}}
    by LW 6/1/2023
    """
    # get direct beam position from CSS:
    pos_dict = {'eiger4m':[eiger4m.beam_center_x.get(),eiger4m.beam_center_y.get()],
                'eiger500k':[eiger500k.beam_center_x.get(),eiger500k.beam_center_y.get()]}
    if detector in list(pos_dict.keys()):
        direct_beam = pos_dict[detector]
        RE.md['beam_position_dict'][detector]['beam_center_x']=direct_beam[0]
        RE.md['beam_position_dict'][detector]['beam_center_y']=direct_beam[1]
        RE.md['beam_position_dict'][detector]['det_x']=saxs_detector.x.user_readback.value
        RE.md['beam_position_dict'][detector]['det_y']=saxs_detector.y.user_readback.value
    else: raise Exception("ERROR: failed to update RE.md['beam_position_dict']")

def calculate_direct_beam_position(detector):
    if detector in ['eiger4m','eiger500k']:
        xshift=(saxs_detector.x.user_readback.value-RE.md['beam_position_dict'][detector]['det_x'])/.075
        yshift=(saxs_detector.y.user_readback.value-RE.md['beam_position_dict'][detector]['det_y'])/.075
        #xpix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_x']+xshift,0))
        #ypix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_y']+yshift,0))
        
        if detector == 'eiger4m':
            xpix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_x']+xshift,0))
            ypix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_y']+yshift,0))
            eiger4m.beam_center_x.set(xpix);eiger4m.beam_center_y.set(ypix)
        elif detector == 'eiger500k':
            xpix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_x']+yshift,0))
            ypix = int(np.round(RE.md['beam_position_dict'][detector]['beam_center_y']-xshift,0))
            eiger500k.beam_center_x.set(xpix),eiger500k.beam_center_y.set(ypix)
        print('New direct beam coordinates for detector: %s: (%s,%s)'%(detector,xpix,ypix))
    else: raise Exception("ERROR: failed to calculate new direct beam position for detector %s"%detector)

def DBPM_feedback(chan_A=True,chan_B=True,xtol=.3,ytol=.3,max_retry=3,stop_on_error=False,check_PID_loop=True,open_shutters=True,verbose=False):
    """
    Macro engages feedback on DBPM.It will try several times to get the beam position to the nominal position if necessary.
    DBPM_feedback(chan_A=True,chan_B=True,max_retry=2,stop_on_error=False,verbose=False)
    chan_A/B = True/False: engage/don't engage feedback on channel A/B
    x/ytol: criteria for feedback successfully engaged: abs(current position-SP) <=x/ytol
    max_retry: maximum number of attempts to get the feedback engaged by cycling feedback ON/OFF
    stop_on_error: if True -> raise exception if the beam cannot be brought to the nominal position or if PID loop is found to be not running
                   if False -> print warning, but continue
    check_PID_loop: check wether PID loop on siepa3p ioc is running or if it needs to be restarted
    by LW 09/13/2023
    11/30/2023 fixed 2 bugs: 1) switch off DBPM chA before checking that PID loop is running; 2) IF NOT checking pid loop, assume pid_loop_running = True
    """
    pid_loop_running = True;pid_loop_check = 'not checked'
    if check_PID_loop:
        # testing PID loop on hdm encoder feedback: 
        # 1) make sure feedback on ch_A and ch_B of DBPM is OFF
        # 2) get current RB value and SP of hdm angle
        # 3) set SP to RB + 2 and engage feedback, wait 3s and check if abs(SP-RB<.2)
        # 4) set SP to old RB, wait to reach position, switch hdm feedback off and restore original SP
        pid_loop_running = False;pid_loop_check = False
        RE(mv(bpm2_feedback_selector_a, 0));RE(mv(bpm2_feedback_selector_b, 0))  #1)
        hdm_RB = caget('XF:11IDA-OP{Mir:HDM-Ax:P}Pos-I'); hdm_SP = caget('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP') #2)
        #3)
        caput('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP',hdm_RB+2); RE(mv(hdm_feedback_selector, 1));RE(sleep(8))
        RB=[]
        for i in range(10): RB.append(caget('XF:11IDA-OP{Mir:HDM-Ax:P}Pos-I'));RE(sleep(.2))
        RB_=np.nanmean(RB)
        if np.abs(caget('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP')-RB_)<=.25:
            pid_loop_running = True; pid_loop_check = False
            if verbose: print('PID loop on sydor ioc seems to be running!')
        else:
            if verbose and (not stop_on_error): print('PID loop on sydor ioc seems to be NOT running!')
            elif stop_on_error: raise Exception('ERROR: PID loop on sydor ioc needs to be restarted')
        #4)
        caput('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP',hdm_RB);RE(sleep(.2))
        RE(mv(hdm_feedback_selector, 1));RE(sleep(8));RE(mv(hdm_feedback_selector, 0))
        caput('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP',hdm_SP)
    else:
        if verbose: print('NOT going to check if PID loop on sydor ioc is running...')
    
    # check if beam is on DBPM
    feedback_possible = False
    if caget('XF:11ID-CT{Peltier:1}bi10'): #at least one shutter before the DBPM is closed
        if open_shutters:
            fe_sh.open();foe_sh.open();pre_sh.open();RE(sleep(3))
        if caget('XF:11ID-CT{Peltier:1}bi10'): # check if any shutter is still closed (that's of course the case if open_shutters=False)
            if verbose and not stop_on_error: print('ERROR: at least one shutter upstream of the DBPM is closed')
            elif stop_on_error:
                raise Exception('ERROR: at least one shutter upstream of the DBPM is closed')
        
    if not caget('XF:11ID-CT{Peltier:1}bi10'): # shutters are open (now), check if there is sufficient intensity on the DBPM
        I_tot = caget('XF:11IDB-BI{XBPM:02}Ampl:CurrTotal-I')
        I_scale =[1,10,100,1000,35000][caget('XF:11IDB-BI{XBPM:02}Gain:Level-SP')]
        I_cutoff = caget('XF:11IDB-BI{XBPM:02}Fdbk:AutoDisableLevel-SP')
        if np.abs(I_tot) >= I_scale*I_cutoff/100:
            feedback_possible = True
            if verbose: print('Intensity on DBPM sufficient to engage feedback.')
        else:
            if verbose and not stop_on_error: print('ERROR: intensity on the DBPM is too low to engage feedback')
            elif stop_on_error:
                raise Exception('ERROR: intensity on the DBPM is too low to engage feedback')

    # engage DBPM feedback (if pre-requisites are met) and check if the beam is in position
    a_SP = caget('XF:11IDB-BI{XBPM:02}Fdbk:A-I');b_SP = caget('XF:11IDB-BI{XBPM:02}Fdbk:B-I');
    in_position = False; pos_list =['a','b'] 
    RE(mv(hdm_feedback_selector, 0)) # encoder feedback on hdm OFF
    for i in range(max_retry):
        if verbose:
            print('try #%s in_position: %s feedback_possible: %s pid_loop_running: %s'%(i,in_position,feedback_possible,pid_loop_running))
        if (not in_position) and feedback_possible and pid_loop_running:
            if 'a' in pos_list:
                RE(mv(bpm2_feedback_selector_a, 0));RE(sleep(.5))
                RE(mv(bpm2_feedback_selector_a, 1))
            if 'b' in pos_list:
                RE(mv(bpm2_feedback_selector_b, 0));RE(sleep(.5))
                RE(mv(bpm2_feedback_selector_b, 1))
            RE(sleep(3));pos_a = [];pos_b=[]
            for i in range(10):
                pos_a.append(caget('XF:11IDB-BI{XBPM:02}Pos:X-I'))
                pos_b.append(caget('XF:11IDB-BI{XBPM:02}Pos:Y-I'));RE(sleep(.2))
            pos_a_ = np.nanmean(pos_a);pos_b_ = np.nanmean(pos_b)
            if np.abs(pos_a_-a_SP)<xtol:
                try:
                    pos_list.remove('a')
                except: pass
            if np.abs(pos_b_-b_SP)<ytol:
                try:
                    pos_list.remove('b')
                except: pass
        if len(pos_list) == 0 and bpm2_feedback_selector_a.get() and bpm2_feedback_selector_b.get():
            in_position = True
    # conclusion:
    if in_position and verbose: print('DBPM successfully engaged, beam in position within xtol= %s & ytol= %s'%(xtol,ytol))
    elif not in_position and verbose and (not stop_on_error):
        print('ERROR: DBPM not engaged, beam position off target!')
    elif not in_position and stop_on_error:
        raise Exception('ERROR: DBPM feedback unable to bring the beam to target position')



def series(det='eiger4m',shutter_mode='single',expt=.1,acqp='auto',imnum=5,comment='', feedback_on=False, PV_trigger=False, position_trigger=False ,analysis='', use_xbpm=False, OAV_mode='none',auto_compression=False,md_import={},auto_beam_position=True):
    """
    det='eiger1m' / 'eiger4m' / 'eiger500k'
    shutter_mode='single' / 'multi'
    expt: exposure time [s]
    acqp: acquire period [s] OR 'auto': acqp=expt
    imnum: number of frames
    feedback_on=False, (True): open fast shutter, switch off feedback on HDM Epics loop, switch on feedback on DBPM
    analysis='' gives a hint to jupyter pipeline to run a certain analysis, e.g. analysis='iso' uses isotropic Q-rings, analysis='qphi' uses phi-sliced Q-rings, etc.
    comment: free comment (string) shown in Olog and attached as RE.md['Measurement']=comment
    update 01/23/2017:  for imnum <100, set chunk size to 10 images to force download. Might still cause problems under certain conditions!!
    yugang add use_xbpm option at Sep 13, 2017 for test fast shutter by using xbpm
    OAV_mode added by LW 01/18/2018: 'none': no image data recorded, 'single': record single image at start of Eiger series, 'start_end': record single image at start and end of Eiger series, 'movie': take contineous stream of images for approximate duration of Eiger series
                added by LW 12/03/2023: 'movie_max': same as movie, but set frame rate equal to current exposure time
    eiger500k added by LW 03/20/2018, Eiger500k multi shutter NOT yet implemented,
              debug by YG 03/22/2018, fix a bug and add Eiger500K multi mode
    03/26/2018: added hook 'analysis' for jupyter pipeline
    10/27/2018: added option to add acquired uid to list for automatic compression:
    auto_compression=False/True, True: add uid to document "general list" in collection "data_acquisition_collection" in database 'samples'
    database access is done in a 'try', to avoid errors in case of problems with database access
    06/03/2019: added trigger via external PV or motor position, with pre-staging of detectors
    PV_trigger = False -> previous behavior, PV_trigger = True: write metadata, stage detector(s), wait for PV trigger signal
    position_trigger = False -> previous behavior
    position_trigger={'motor':diff.xh,'target':-.2,'threshold':.1,'start_move':False} -> trigger when motor position within threshold,
    start_move=False -> don't move motor from series, start_move=True: move motor from series
    10/02/2020: collect series specific md in dictionary and use md in count to capture it; add possibility to pass md dictionary to series; 
    add auto-comment: comment='descr1'+'AUTO_COMMENT'+'descr2' -> 'descr1 expt=xxxs, imnum=yyyy, Trans= zzz sample: RE.md['sample'] descr2
    auto_beam_position: if True, updates PVs for direct beam position based on reference positions in RE.md['beam_position_dict'] and current detector position
    """
    # Define trigger PV (use is optional)
    #caput('XF:11ID-CT{ES:1}bo2',1)
    #trigger_pv='XF:11ID-CT{ES:1}bi3'
    trigger_pv = 'XF:11ID-CT{M3}bi2' # standard, used for HD 3D printer (-m3)
    #trigger_pv = 'XF:11IDB-ES{IO:1}DI:1-Sts'   # digitial input DI0 -> used e.g. for Linkam trigger
    #trigger_pv='XF:11ID-CT{ES:1}bi1' 
    #trigger_pv='XF:11IDB-ES{IO}DI:4-Sts' #linkam trigger
    trigger_PV=EpicsSignal(trigger_pv,name='trigger_PV')
   
    
    if PV_trigger and position_trigger:
      raise series_Exception('error: Cannot trigger both at PV signal and motor position -> chose one!')
    
    print('start of series: '+time.ctime())
    
    # check if acquire period should be equal to exposure time:
    if acqp=='auto':
        acqp=expt
    
    if auto_beam_position and 'eiger1m' not in det:     # update direct beam position based on md reference and current detector position
        calculate_direct_beam_position(det)

    #check for maxiumum frame rates (and correct if higher...might be redundant to what is done on the Dectris driver level, but ensures consistent md):
    freq_dict={'eiger1m':.00034,'eiger4m':.0007,'eiger500k':.000112}
    if acqp < freq_dict[det]:
        acqp=freq_dict[det]
    
    PV_dict={'eiger1m':'Eig1M','eiger4m':'Eig4M','eiger500k':'Eig500K'}
    
    # get path and sequence ID for md, reset image counter:
    seqid=caget('XF:11IDB-ES{Det:%s}cam1:SequenceId'%PV_dict[det])+1 #get Dectris sequence ID
    idpath=caget('XF:11IDB-ES{Det:%s}cam1:FilePath'%PV_dict[det],' {"longString":true}')
    
    # remove files from detector, reset image counter:
    if caget('XF:11IDB-ES{Det:%s}cam1:FWAutoRemove_RBV'%PV_dict[det]) != 1:
        caput('XF:11IDB-ES{Det:%s}cam1:FWClear'%PV_dict[det],1,wait=True)    #remove files from the detector
    caput('XF:11IDB-ES{Det:%s}cam1:ArrayCounter'%PV_dict[det],0) # set image counter to '0'
    
    # set HDF5 file chunk size:
    if imnum < 10:
            caput('XF:11IDB-ES{Det:%s}cam1:FWNImagesPerFile'%PV_dict[det],1)
    elif imnum < 100:                                                            
            caput('XF:11IDB-ES{Det:%s}cam1:FWNImagesPerFile'%PV_dict[det],10)
    elif imnum < 1000:                                                            
            caput('XF:11IDB-ES{Det:%s}cam1:FWNImagesPerFile'%PV_dict[det],100)
    else: 
            caput('XF:11IDB-ES{Det:%s}cam1:FWNImagesPerFile'%PV_dict[det],1000)


    if shutter_mode=='single':
        if det == 'eiger1m':
            detector=eiger1m_single
        if det == 'eiger4m':
            detector=eiger4m_single
        if det == 'eiger500k':            
            detector=eiger500k_single

        detector.cam.acquire_time.value=expt       # setting up exposure for eiger500k/1m/4m_single
        detector.cam.acquire_period.value=acqp
        detector.cam.num_images.value=imnum
        
    else:
        raise series_Exception('error: this macro currently only supports single shutter mode')

    #print('adding experiment specific metadata: '+time.ctime())
    ## add series specific metadata:
    
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 1 or feedback_on == True:
        fx='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 0:
        fx='off'
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 1 or feedback_on == True:
        fy='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 0: 
        fy='off'
    
    # create series specific md dictionary
    transmission=att.get_T()*att2.get_T()
    T_yoke=str(caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I'))
    T_sample=str(caget('XF:11IDB-ES{Env:01-Chan:D}T:C-I'))
    T_sample_stinger = str(caget('XF:11IDB-ES{Env:02}LS340:TC1:Sample')) #Xiao added Apr 29 2022
    #md_series={'exposure time':str(expt), 'acquire period':str(acqp),'shutter mode':shutter_mode,'number of images':str(imnum),'data path':idpath,'sequence id':str(seqid),
                  #'transmission':transmission,'OAV_mode':OAV_mode,'T_yoke':T_yoke,'T_sample':T_sample,'analysis':analysis,'feedback_x':fx,'feedback_y':fy}
    #Xiao added 'T_sample_stinger'
    md_series={'XPCS_data':True,'exposure time':str(expt), 'acquire period':str(acqp),'shutter mode':shutter_mode,'number of images':str(imnum),'data path':idpath,'sequence id':str(seqid),
                  'transmission':transmission,'OAV_mode':OAV_mode,'T_yoke':T_yoke,'T_sample':T_sample,'T_sample_stinger':T_sample_stinger,'analysis':analysis,'feedback_x':fx,'feedback_y':fy}

    ## end series specific metadata
    ## merge with md_import, dublicate keys will be converted to string and add '_' in md_import
    double_keys=list(set(md_series).intersection(md_import))
    for dk in double_keys:
        md_import['%s_'%dk]=md_import[dk]
    md_import.update(md_series)
    
    # generate automatic comment for olog   
    if 'AUTO_COMMENT' in comment:
        ac='%ss x %s fr. Trans:%s sample: %s'%(expt,imnum,transmission,RE.md['sample'])
        cl=comment.split('AUTO_COMMENT')
        if len(cl)==1:
            if comment[0:12]=='AUTO_COMMENT': # format: auto_comment + custom comment
                total_comment='%s %s'%(ac,cl[0])
            else: total_comment='%s %s'%(cl[0],ac)  # format: custom comment + auto_comment
        else: total_comment='%s %s %s'%(cl[0],ac,cl[1])
    else: total_comment=comment
    
    print('taking data series: exposure time: '+str(expt)+'s,  period: '+str(acqp)+'s '+str(imnum)+'frames  shutter mode: '+shutter_mode)
    print('Dectris sequence id: '+str(int(seqid)))
    
    
    print('OAV_mode: '+OAV_mode)    ### ADDED OAV_mode HERE!
    
    if OAV_mode not in ['none','single','start_end','movie', 'movie_max']:
        raise series_Exception('error: OAV_mode needs to be none|single|start_end|movie|movie_max...')
    
    if OAV_mode == 'none':
        detlist=[detector]
    else:
        detlist=[detector,OAV_writing]
        OAV.cam.acquire.set(0) # stop camera and set mode to multiple, otherwise something is resetting the number of images...
        OAV.cam.image_mode.set(1)
        org_pt=OAV.cam.acquire_period.get() 
        org_ni=OAV.cam.num_images.get()
        org_acqt = OAV.cam.acquire_time.get()
    
    if OAV_mode == 'single':
        OAV.cam.num_images.put(2,wait=True) ## if switching on light, first image will be dark
    if OAV_mode == 'start_end': 
        pt=(acqp)*imnum #period between two images to span Eiger series (exposure time for OAV image neglected)
        OAV.cam.num_images.put(2,wait=True)
        OAV.cam.acquire_period.put(pt,wait=True)
    if OAV_mode == 'movie_max':
        OAV.cam.acquire_period.put(OAV.cam.acquire_time.get(),wait=True)
    if OAV_mode == 'movie' or OAV_mode == 'movie_max':
        ni=acqp*imnum/OAV.cam.acquire_period.get()
        ni=ni-ni*.2
        OAV.cam.num_images.put(np.ceil(ni),wait=True)
        
    if use_xbpm:
        caput( 'XF:11IDB-BI{XBPM:02}FaSoftTrig-SP',1,wait=True) #yugang add at Sep 13, 2017 for test fast shutter by using xbpm
        print('Use XBPM to monitor beam intensity.')

    if PV_trigger:
      dets = detlist     
      #RE(wait_for_pv(dets,trigger_PV,feedback_on=feedback_on,md=md_import),Measurement=total_comment)
      print('md dictionary: %s'%md_import)
      RE(wait_for_pv(dets,trigger_PV,feedback_on=feedback_on,md=md_import),Measurement=total_comment)
    elif position_trigger:
      dets = detlist     
      #RE(wait_for_motor(dets, position_trigger['motor'], position_trigger['target'], position_trigger['threshold'],start_move=position_trigger['start_move'], feedback_on=feedback_on, md=md_import),Measurement=total_comment) 
      RE(wait_for_motor(dets, position_trigger['motor'], position_trigger['target'], position_trigger['threshold'],start_move=position_trigger['start_move'], md=md_import),Measurement=total_comment) 

    else:
      if feedback_on:
        #RE(prep_series_feedback()) -> OLD FAST SHUTTER UPSTREAM OF DBPM
        if (not bpm2_feedback_selector_a.get()) or (not bpm2_feedback_selector_b.get()): # feedback isn't already running
            DBPM_feedback(chan_A=True,chan_B=True,xtol=.3,ytol=.3,max_retry=3,stop_on_error=False,check_PID_loop=False,open_shutters=False,verbose=False)
      RE(count(detlist,md=md_import),Measurement=total_comment)  ### TAKING DATA
    
    # setting image number and period back for OAV camera:
    if OAV_mode != 'none':    
        OAV.cam.num_images.set(org_ni)
        OAV.cam.acquire_period.set(org_pt)
        OAV.cam.acquire_time.set(org_acqt)
        # also -at least temporarily- need to set mode back and restart acquisition.
        OAV.cam.image_mode.put(2)
        OAV.cam.acquire.put(1)
    
    ####### add acquired uid to database list for automatic compression #########
    if auto_compression:
        try:
            #scan_add = None
            #for l in range(10): # with multithreading, other uids might have completed before this one, e.g. with Pilatus 800k WAXS detector -> need to find last uid that uses same detector as this series
            #    if scan_add is None:
            #        h=db[-(l+1)]
            #        #for d in range(len(h.start['plan_args']['detectors'])):
            #        if detector.name in list(h.devices()): scan_add=l+1
            #uid_add=db[-scan_add]['start']['uid']
            uid_add=db[-1]['start']['uid']
            uid_list=data_acquisition_collection.find_one({'_id':'general_list'})['uid_list']
            uid_list.append(uid_add)          
            data_acquisition_collection.update_one({'_id': 'general_list'},{'$set':{'uid_list' : uid_list}})
            print('Added uid %s to list for automatic compression!'%uid_add)
        except:
            try:
                print('Sorry, failed to add uid %s to list for automatic compression!'%uid_add)
            except: # in case we cannot find uid_add at all
                print('Sorry, failed to add uid to list for automatic compression!')
    else:
        print('uid not added to database for automatic compression')
    ############################################################################### THE END #########################


def check_uid():
    scan_add = None
    for l in range(10): # with multithreading, other uids might have completed before this one, e.g. with Pilatus 800k WAXS detector -> need to find last uid that uses same detector as this series
        print(l)
        if scan_add is None:
            h=db[-(l+1)]
            for d in range(len(h.start['plan_args']['detectors'])):
                if detector.name in h.start['plan_args']['detectors'][d]: scan_add=l+1
    uid_add=db[-scan_add]['start']['uid']   

    
    
# Lutz's test Nov 08 start OBSOLETE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
def series_old(det='eiger4m',shutter_mode='single',expt=.1,acqp='auto',imnum=5,comment='', feedback_on=False, PV_trigger=False, position_trigger=False ,analysis='', use_xbpm=False, OAV_mode='none',auto_compression=False,*argv, **kwargs):
    """
    det='eiger1m' / 'eiger4m' / 'eiger500k'
    shutter_mode='single' / 'multi'
    expt: exposure time [s]
    acqp: acquire period [s] OR 'auto': acqp=expt
    imnum: number of frames
    feedback_on=False, (True): open fast shutter, switch off feedback on HDM Epics loop, switch on feedback on DBPM
    analysis='' gives a hint to jupyter pipeline to run a certain analysis, e.g. analysis='iso' uses isotropic Q-rings, analysis='qphi' uses phi-sliced Q-rings, etc.
    comment: free comment (string) shown in Olog and attached as RE.md['Measurement']=comment
    update 01/23/2017:  for imnum <100, set chunk size to 10 images to force download. Might still cause problems under certain conditions!!
    yugang add use_xbpm option at Sep 13, 2017 for test fast shutter by using xbpm
    OAV_mode added by LW 01/18/2018: 'none': no image data recorded, 'single': record single image at start of Eiger series, 'start_end': record single image at start and end of Eiger series, 'movie': take contineous stream of images for approximate duration of Eiger series
    eiger500k added by LW 03/20/2018, Eiger500k multi shutter NOT yet implemented,
              debug by YG 03/22/2018, fix a bug and add Eiger500K multi mode
    03/26/2018: added hook 'analysis' for jupyter pipeline
    10/27/2018: added option to add acquired uid to list for automatic compression:
    auto_compression=False/True, True: add uid to document "general list" in collection "data_acquisition_collection" in database 'samples'
    database access is done in a 'try', to avoid errors in case of problems with database access
    06/03/2019: added trigger via external PV or motor position, with pre-staging of detectors
    PV_trigger = False -> previous behavior, PV_trigger = True: write metadata, stage detector(s), wait for PV trigger signal
    position_trigger = False -> previous behavior
    position_trigger={'motor':diff.xh,'target':-.2,'threshold':.1,'start_move':False} -> trigger when motor position within threshold,
    start_move=False -> don't move motor from series, start_move=True: move motor from series
    """
    #timing delay between calling series and start of data acquisition:
    #caput('XF:11ID-CT{ES:1}bo2',1)
    #trigger_pv='XF:11ID-CT{ES:1}bi3'
    #trigger_pv = 'XF:11ID-CT{M1}bi4' # standard, used for 3D printing
    trigger_pv = 'XF:11IDB-ES{IO:1}DI:1-Sts'   # digitial input DI0 -> used e.g. for Linkam trigger 
    trigger_PV=EpicsSignal(trigger_pv,name='trigger_PV')
    
    if PV_trigger and position_trigger:
      raise series_Exception('error: Cannot trigger both at PV signal and motor position -> chose one!')
    
    print('start of series: '+time.ctime())
    
    
    PV_dict={'eiger1m':'Eig1M','eiger4m':'Eig4M','eiger500k':'Eig500k'}
    if 'save_files' in kwargs.keys():  # added: option to save/not save files
        save_files= kwargs['save_files']
    else:
        save_files=True
        
    if save_files:
        caput('XF:11IDB-ES{Det:%s}cam1:FWEnable'%PV_dict[det],1)
    elif not save_files:
        caput('XF:11IDB-ES{Det:%s}cam1:FWEnable'%PV_dict[det],0)
        auto_compression=False
        print('WARNING: NOT SAVING FILES!!! ')
        comment='WARNING: NOT SAVING FILES!!! '+comment
    else:
        raise series_Exception('error: unknown optional keyword argment "%s" for "save_file". Valid options are True/False'%kwargs['save_files'])
    
    
    if acqp=='auto':
        acqp=expt
    if det == 'eiger1m':    #get Dectris sequence ID
        if acqp <.00034:
            acqp=.00034
        else:
            pass
        seqid=caget('XF:11IDB-ES{Det:Eig1M}cam1:SequenceId')+1
        idpath=caget('XF:11IDB-ES{Det:Eig1M}cam1:FilePath',' {"longString":true}')
        caput('XF:11IDB-ES{Det:Eig1M}cam1:FWClear',1)    #remove files from the detector
        caput('XF:11IDB-ES{Det:Eig1M}cam1:ArrayCounter',0) # set image counter to '0'
        if imnum < 10:
            caput('XF:11IDB-ES{Det:Eig1M}cam1:FWNImagesPerFile',1)
        elif imnum < 500:                                                            # set chunk size
            caput('XF:11IDB-ES{Det:Eig1M}cam1:FWNImagesPerFile',10)
        else: 
            caput('XF:11IDB-ES{Det:Eig1M}cam1:FWNImagesPerFile',100)
    elif det == 'eiger4m':
        if acqp <.00134:
            acqp=.00134
        else:
            pass
        seqid=caget('XF:11IDB-ES{Det:Eig4M}cam1:SequenceId')+1
        idpath=caget('XF:11IDB-ES{Det:Eig4M}cam1:FilePath',' {"longString":true}')
        caput('XF:11IDB-ES{Det:Eig4M}cam1:FWClear',1)    #remove files from the detector DISABLED FOR MANUAL DOWNLOAD!!!
        caput('XF:11IDB-ES{Det:Eig4M}cam1:ArrayCounter',0) # set image counter to '0'
        if imnum < 500:                                                            # set chunk size
            caput('XF:11IDB-ES{Det:Eig4M}cam1:FWNImagesPerFile',10)
        else: 
            caput('XF:11IDB-ES{Det:Eig4M}cam1:FWNImagesPerFile',100)
    elif det == 'eiger500k':
        if acqp <.000112:
            acqp=.000112
        else:
            pass
        seqid=caget('XF:11IDB-ES{Det:Eig500K}cam1:SequenceId')+1
        idpath=caget('XF:11IDB-ES{Det:Eig500K}cam1:FilePath {"longString":true}')
        caput('XF:11IDB-ES{Det:Eig500K}cam1:FWClear',1)    #remove files from the detector DISABLE FOR MANUAL DOWNLOAD!!!
        caput('XF:11IDB-ES{Det:Eig500K}cam1:ArrayCounter',0) # set image counter to '0'
        if imnum < 500:                                                            # set chunk size
            caput('XF:11IDB-ES{Det:Eig500K}cam1:FWNImagesPerFile',10)
        else: 
            caput('XF:11IDB-ES{Det:Eig500K}cam1:FWNImagesPerFile',100)
    #print('setting detector paramters: '+time.ctime())
    if acqp=='auto':
        acqp=expt


    if shutter_mode=='single':
        if det == 'eiger1m':
            detector=eiger1m_single
        if det == 'eiger4m':
            detector=eiger4m_single
        if det == 'eiger500k':            
            detector=eiger500k_single

        detector.cam.acquire_time.value=expt       # setting up exposure for eiger500k/1m/4m_single
        detector.cam.acquire_period.value=acqp
        detector.cam.num_images.value=imnum
        #print('adding metadata: '+time.ctime())
        RE.md['exposure time']=str(expt)        # add metadata information about this run
        RE.md['acquire period']=str(acqp)
        RE.md['shutter mode']=shutter_mode
        RE.md['number of images']=str(imnum)
        RE.md['data path']=idpath
        RE.md['sequence id']=str(seqid)
        RE.md['transmission']=att.get_T()*att2.get_T()
        RE.md['OAV_mode']=OAV_mode
    if shutter_mode=='multi':
#        if 1./acqp*1E3>51000:           # check for fast shutter / vacuum issues....
#            raise series_Exception('error: due to vacuum issues, 1/acqp*1000 !<51000 ')
#        if caget('XF:11IDB-VA{Att:1-CCG:1}P-I') > 8.E-8:
#            print('vacuum in fast shutter section is bad: '+str(caget('XF:11IDB-VA{Att:1-CCG:1}P-I'))+' Torr (need: 8.E-8 Torr)...'+time.ctime()+': going to wait for 15 min!')
#            sleep(900)
#            if caget('XF:11IDB-VA{Att:1-CCG:1}P-I') > 8.E-8:
#                print('vacuum in fast shutter section is bad: '+str(caget('XF:11IDB-VA{Att:1-CCG:1}P-I'))+' Torr -> still bad, going to abort!')
#                raise series_Exception('error: vacuum issue in the fast shutter section...aborting run.')
#            else: print('vacuum level: '+str(caget('XF:11IDB-VA{Att:1-CCG:1}P-I'))+' Torr -> pass!')
        if acqp <.1 and imnum > 5000:
                print('warning: max number frames with shutter >10Hz is 5000....re-setting "imnum" to 5000.')
                imnum=5000
        if expt*acqp < 5.99E-5:
                raise series_Exception('error: shutter duty cycle is too high...make sure expt x acqp <6E-5.')
        if det == 'eiger1m':
            detector=eiger1m
            if expt+caget('XF:11IDB-ES{Det:Eig1M}ExposureDelay-SP') >= acqp or acqp<.019:   # check whether requested parameters are sensible
                raise series_Exception('error: exposure time +shutter time > acquire period or shutter requested to go >50Hz')
            
            caput('XF:11IDB-ES{Det:Eig1M}Mode-Cmd',1)    #enable auto-shutter-mode
            caput('XF:11IDB-ES{Det:Eig1M}NumImages-SP',imnum)
            caput('XF:11IDB-ES{Det:Eig1M}ExposureTime-SP',expt)
            caput('XF:11IDB-ES{Det:Eig1M}AcquirePeriod-SP',acqp)
            detector.cam.acquire_period.value=acqp   # ignored in data acquisition, but gets correct metadata in HDF5 file
        if det == 'eiger4m':
            detector=eiger4m
            if expt+caget('XF:11IDB-ES{Det:Eig4M}ExposureDelay-SP') >= acqp or acqp<.019:
                raise series_Exception('error: exposure time +shutter time > acquire period or shutter requested to go >50Hz')
            caput('XF:11IDB-ES{Det:Eig4M}Mode-Cmd',1)    #enable auto-shutter-mode
            caput('XF:11IDB-ES{Det:Eig4M}NumImages-SP',imnum)
            caput('XF:11IDB-ES{Det:Eig4M}ExposureTime-SP',expt)
            caput('XF:11IDB-ES{Det:Eig4M}AcquirePeriod-SP',acqp)
            detector.cam.acquire_period.value=acqp   # ignored in data acquisition, but gets correct metadata in HDF5 file

        if det == 'eiger500k':
            detector=eiger500k

            if expt+caget('XF:11IDB-ES{Det:Eig500K}ExposureDelay-SP') >= acqp or acqp<.019:
                raise series_Exception('error: exposure time +shutter time > acquire period or shutter requested to go >50Hz')
            caput('XF:11IDB-ES{Det:Eig500K}Mode-Cmd',1)    #enable auto-shutter-mode
            caput('XF:11IDB-ES{Det:Eig500K}NumImages-SP',imnum)
            caput('XF:11IDB-ES{Det:Eig500K}ExposureTime-SP',expt)
            caput('XF:11IDB-ES{Det:Eig500K}AcquirePeriod-SP',acqp)
            detector.cam.acquire_period.value=acqp   # ignored in data acquisition, but gets correct metadata in HDF5 file
            #print('here')

        RE.md['exposure time']=expt        # add metadata information about this run
        RE.md['acquire period']=acqp
        RE.md['shutter mode']=shutter_mode
        RE.md['number of images']=imnum
        RE.md['data path']=idpath
        RE.md['sequence id']=str(seqid)
        RE.md['transmission']=att.get_T()*att2.get_T()
        RE.md['OAV_mode']=OAV_mode
        
    #print('adding experiment specific metadata: '+time.ctime())
    ## add experiment specific metadata:
    RE.md['T_yoke']=str(caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I'))
    RE.md['T_sample']=str(caget('XF:11IDB-ES{Env:01-Chan:D}T:C-I'))
    RE.md['analysis']=analysis
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 1 or feedback_on == True:
        RE.md['feedback_x']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP') == 0:
        RE.md['feedback_x']='off'
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 1 or feedback_on == True:
        RE.md['feedback_y']='on'
    elif caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP') == 0: 
        RE.md['feedback_y']='off'
    ## end experiment specific metadata
    print('taking data series: exposure time: '+str(expt)+'s,  period: '+str(acqp)+'s '+str(imnum)+'frames  shutter mode: '+shutter_mode)
    print('Dectris sequence id: '+str(int(seqid)))
    #print('executing count: '+time.ctime())
    print('OAV_mode: '+OAV_mode)    ### ADDED OAV_mode HERE!
    if OAV_mode == 'none':
        detlist=[detector]
    elif OAV_mode == 'single':
        if save_files:
            detlist=[detector,OAV_writing] 
        else:
            detlist=[detector,OAV] 
        #detlist=[detector,OAV] ## NOT saving...for debugging only
        org_pt=caget('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod_RBV')
        org_ni=caget('XF:11IDB-BI{Cam:10}cam1:NumImages_RBV')
        caput('XF:11IDB-BI{Cam:10}cam1:NumImages',2,wait=True)  ## if switching on light, first image will be dark
    elif OAV_mode == 'start_end':
        if save_files:
            detlist=[detector,OAV_writing] 
        else:
            detlist=[detector,OAV] 
        #detlist=[detector,OAV] ## NOT saving...for debugging only
        org_pt=caget('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod_RBV')
        org_ni=caget('XF:11IDB-BI{Cam:10}cam1:NumImages_RBV')        
        pt=(acqp)*imnum #period between two images to span Eiger series (exposure time for OAV image neglected)
        caput('XF:11IDB-BI{Cam:10}cam1:NumImages',2,wait=True)
        caput('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod',pt,wait=True)
    elif OAV_mode == 'movie':
        if save_files:
            detlist=[detector,OAV_writing] 
        else:
            detlist=[detector,OAV] 
        #detlist=[detector,OAV] ## NOT saving...for debugging only
        org_pt=caget('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod_RBV')
        org_ni=caget('XF:11IDB-BI{Cam:10}cam1:NumImages_RBV')
        ni=acqp*imnum/caget('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod')
        ni=ni+ni/10
        caput('XF:11IDB-BI{Cam:10}cam1:NumImages',np.ceil(ni),wait=True)
    else: raise series_Exception('error: OAV_mode needs to be none|single|start_end|movie...')
    if use_xbpm:
        caput( 'XF:11IDB-BI{XBPM:02}FaSoftTrig-SP',1,wait=True) #yugang add at Sep 13, 2017 for test fast shutter by using xbpm
        print('Use XBPM to monitor beam intensity.')

    #RE(count([detector]),Measurement=comment)  ### ACQUISITION
    if PV_trigger:
      dets = detlist     
      RE(wait_for_pv(dets,trigger_PV,feedback_on=feedback_on,md=RE.md),Measurement=comment)
    elif position_trigger:
      dets = detlist     
      RE(wait_for_motor(dets, position_trigger['motor'], position_trigger['target'], position_trigger['threshold'],start_move=position_trigger['start_move'], feedback_on=feedback_on, md=RE.md),Measurement=comment) 
    else:
      if feedback_on:
        RE(prep_series_feedback())
      RE(count(detlist),Measurement=comment)  ### testing camera images taken simultaneously
    # setting image number and period back for OAV camera:
    if OAV_mode != 'none':      ####! OAV !!!!!
        caput('XF:11IDB-BI{Cam:10}cam1:NumImages',org_ni)
        caput('XF:11IDB-BI{Cam:10}cam1:AcquirePeriod',org_pt)
    ####### add acquired uid to database list for automatic compression #########
    if auto_compression:
        try:
            uid_add=db[-1]['start']['uid']
            uid_list=data_acquisition_collection.find_one({'_id':'general_list'})['uid_list']
            uid_list.append(uid_add)
            data_acquisition_collection.update_one({'_id': 'general_list'},{'$set':{'uid_list' : uid_list}})
            print('Added uid %s to list for automatic compression!'%uid_add)
        except:
            print('Sorry, failed to add uid %s to list for automatic compression!'%uid_add)
    else:
        print('uid not added to database for automatic compression')
    ###############################################################################
    # remove series specific keys from general metadata:
    for ke in ['exposure time','acquire period','shutter mode','number of images','sequence id','T_yoke','T_sample','feedback_x','feedback_y','transmission','OAV_mode','analysis', 'data path']:
    	del RE.md[ke]



class series_Exception(Exception):
    pass

## Peltier cooler
class Peltier_Cooler(Device):
    enable_command = Cpt(EpicsSignal, 'B-ES{Pel-IO:1}DO:1-Cmd')
    enable_status = Cpt(EpicsSignal, 'B-ES{Pel-IO:1}DO:1-Sts')
    set_power_command = Cpt(EpicsSignal, '-CT{Peltier:1}ai2')
    setup_power = Cpt(EpicsSignal, '-CT{Peltier:1}ai2.DESC')
    setup_hot_side_max = Cpt(EpicsSignal, '-CT{Peltier:1}ai3.DESC')
    set_hot_side_max = Cpt(EpicsSignal, '-CT{Peltier:1}ai3')
    setup_chiller_temperature = Cpt(EpicsSignal, '-CT{Peltier:1}ai1.DESC')
    set_chiller_temperature = Cpt(EpicsSignal, '-CT{Peltier:1}ai1')
    setup_peltier_enabled = Cpt(EpicsSignal, '-CT{Peltier:1}bi9.DESC')

    def enable(self):
        self.enable_command.put(1)
        print('Peltier Power enabled.')
        
    def disable(self):
        self.enable_command.put(0,use_complete=True)
        print('Peltier Power diabled.')
            
    def power(self,P):
        self.set_power_command.put(P)
        print('Peltier Power set to: %s percent'%P)
        
    def status(self):
        return print('Peltier enabled: %s   Peltier Power: %s percent'%(bool(self.enable_status.get()),self.set_power_command.get()))
    
    def setup(self):
        self.setup_chiller_temperature.put('chiller temp. [12-22C]')
        self.set_chiller_temperature.put(22)
        self.setup_power.put('Peltier Power [0-100%]')
        self.set_power_command.put(0)
        self.setup_hot_side_max.put('Pel. hot side max T [C]')
        self.set_hot_side_max.put(17.5)
        self.setup_peltier_enabled.put('Peltier ENABLED')
    
    def chiller_temperature(self,T):
        self.set_chiller_temperature.put(T)
        print('Chiller temperature set to: %s [C]'%T)





peltier = Peltier_Cooler('XF:11ID',name='peltier')


  
# heating with sample chamber, using both heaters:
def set_temperature(Tsetpoint,heat_ramp=3,cool_ramp=0,log_entry='on',check_vac=True):       # MADE MAJOR CHANGES: NEEDS TESTING!!! [01/23/2017 LW]
    """
    heating with sample chamber, using both heaters
    macro maintains 40deg difference between both heaters to have a temperature gradient for stabilization
    Tsetpoint: temperature setpoint in deg Celsius!
    heat_ramp: ramping speed [deg.C/min] on heating. Currently a ramp with max 3deg.C/min will be enforced!
    cool_ramp: ramping speed [deg.C/min] on cooling. '0' -> ramp off!
    log_entry: 'on' / 'off'  -> make olog entry when changing temperature ('try', ignored, if Olog is down...)
    check_vac: True/False -> checks for vacuum level on hard-coded PV for temperatures > 50C or <10C
    """
    vac_check_PV='XF:11IDB-VA{Samp:1-TCG:1}P-I'
    if check_vac:
        vac=caget(vac_check_PV)
        if vac > .1:
            raise ValueError('vacuum in sample chamber needs to be better than .1 for T>50C or T<10C!')
        else:
            print('vacuum in sample chamber: %s Torr -> passed vacuum check!'%vac)
    
    if heat_ramp > 7.:
        heat_ramp=7.
    else: pass
    if cool_ramp==0:
        cool_ramp_on=0
    else:  cool_ramp_on=1
    
    start_T=caget('XF:11IDB-ES{Env:01-Chan:C}T:C-I')
    start_T2=caget('XF:11IDB-ES{Env:01-Chan:B}T:C-I')
    if start_T >= Tsetpoint:        # cooling requested 
        caput('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel',0)  # ramp off
        caput('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel',0)                          
        caput('XF:11IDB-ES{Env:01-Out:1}T-SP',273.15+start_T)    # start from current temperature
        caput('XF:11IDB-ES{Env:01-Out:2}T-SP',273.15+start_T2)
        if cool_ramp==0:                                                                                # print message and make Olog entry, if requested
            print('cooling Channel C to '+str(Tsetpoint)+'deg, no ramp')
            RE(sleep(5))  # need time to update setpoint....
            if log_entry == 'on':
                try:
                    olog_client.log( 'Changed temperature to T='+ str(Tsetpoint)[:5]+'C, ramp: off')
                except:
                    pass
            else: pass
        elif cool_ramp >0:
            print('cooling Channel C to '+str(Tsetpoint)+'deg @ '+str(cool_ramp)+'deg./min')    
            if log_entry == 'on':
                try:
                    olog_client.log( 'Changed temperature to T='+ str(Tsetpoint)[:5]+'C, ramp: '+str(cool_ramp)+'deg./min')
                except:
                    pass
            else: pass
        #caput('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel',cool_ramp_on)        #switch ramp on/off as requested
        #caput('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel',cool_ramp_on)
        caput('XF:11IDB-ES{Env:01-Out:1}Val:Ramp-SP',cool_ramp,wait=True)   # set ramp to requested value
        caput('XF:11IDB-ES{Env:01-Out:2}Val:Ramp-SP',cool_ramp,wait=True)
        RE(sleep(5))
        caput('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel',cool_ramp_on,wait=True)        #switch ramp on/off as requested
        caput('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel',cool_ramp_on,wait=True)
        caput('XF:11IDB-ES{Env:01-Out:1}T-SP',273.15+Tsetpoint)    # setting channel C to Tsetpoint
        caput('XF:11IDB-ES{Env:01-Out:2}T-SP',233.15+Tsetpoint) # setting channel B to Tsetpoint-40C
    elif start_T<Tsetpoint:        #heating requested, ramp on
        print('heating Channel C to '+str(Tsetpoint)+'deg @ '+str(heat_ramp)+'deg./min')
        RE(sleep(5))    
        if log_entry == 'on':
            try:
                olog_client.log( 'Changed temperature to T='+ str(Tsetpoint)[:5]+'C, ramp: '+str(heat_ramp)+'deg./min')
            except:
                pass
        else: pass
        caput('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel',0,wait=True)  # ramp off
        caput('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel',0,wait=True)
        caput('XF:11IDB-ES{Env:01-Out:1}T-SP',273.15+start_T)    # start from current temperature
        caput('XF:11IDB-ES{Env:01-Out:2}T-SP',273.15+start_T2)
        caput('XF:11IDB-ES{Env:01-Out:1}Val:Ramp-SP',heat_ramp,wait=True)   # set ramp to selected value or allowed maximum
        caput('XF:11IDB-ES{Env:01-Out:2}Val:Ramp-SP',heat_ramp,wait=True)
        #print('flashed yet??')
        #RE(sleep(5))
        caput('XF:11IDB-ES{Env:01-Out:1}Out:MaxI-SP',1.0) # force max current to 1.0 Amp
        caput('XF:11IDB-ES{Env:01-Out:2}Out:MaxI-SP',.7)
        caput('XF:11IDB-ES{Env:01-Out:1}Val:Range-Sel',3) # force heater range 3 -> should be able to follow 2deg/min ramp
        caput('XF:11IDB-ES{Env:01-Out:2}Val:Range-Sel',3)
        RE(sleep(5))
        caput('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel',1,wait=True)  # ramp on
        caput('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel',1,wait=True)
        caput('XF:11IDB-ES{Env:01-Out:1}T-SP',273.15+Tsetpoint)    # setting channel C to Tsetpoint
        caput('XF:11IDB-ES{Env:01-Out:2}T-SP',233.15+Tsetpoint) # setting channel B to Tsetpoint-40C
    RE(sleep(60)) # some things are notoriously slow to update, this sleep ensures that wait_temperature() is waiting for the correct target temperature


# wait for temperature NOT TESTED YET
def wait_temperature(wait_time=1200,dead_band=1.,channel=1,log_entry='on'):
    """
    """
    sleep(5) # make sure previous changes to the Lakehsore settings are updated...
    ch=['none','XF:11IDB-ES{Env:01-Chan:A}T:C-I','XF:11IDB-ES{Env:01-Chan:B}T:C-I','XF:11IDB-ES{Env:01-Chan:C}T:C-I','XF:11IDB-ES{Env:01-Chan:D}T:C-I']
    #check on which temperature the selected channel feedbacks:
    if channel==1:
        ch_num=caget('XF:11IDB-ES{Env:01-Out:1}Out-Sel')
        ramp=caget('XF:11IDB-ES{Env:01-Out:1}Val:Ramp-RB')
        T_set=caget('XF:11IDB-ES{Env:01-Out:1}T-SP') - 273.15
        ramp_on=caget('XF:11IDB-ES{Env:01-Out:1}Enbl:Ramp-Sel')
    elif channel==2:
        ch_num=caget('XF:11IDB-ES{Env:01-Out:2}Out-Sel')
        ramp=caget('XF:11IDB-ES{Env:01-Out:2}Val:Ramp-RB')
        T_set=caget('XF:11IDB-ES{Env:01-Out:2}T-SP') - 273.15
        ramp_on=caget('XF:11IDB-ES{Env:01-Out:2}Enbl:Ramp-Sel')
    else: raise check_Exception('error: control channel has to be either "1" or "2"!')
    curr_T=caget(ch[ch_num])
    # estimate how long it will take to reach the temperature setpoint:
    if ramp_on==1:
        try:
            dtime=abs(T_set-curr_T)/ramp
        except:
            print('could not estimate time to reach target temperature...')
            dtime=999.
    else:
        print('temperature ramping is off...checking temperature increase vs. time...this will take several minutes....')
        sleep(120) # wait 2 minutes (overcome T-inertia)
        dtime=get_T_gradient(channel)
    print(time.ctime()+ '   initial estimate to reach T='+str(T_set)[:5]+'C on channel '+caget('XF:11IDB-ES{Env:01-Out:1}Out-Sel','char')+': '+str(dtime)[:5]+' minutes')
    # initial wait for reaching setpoint temperature
    dT=T_set-caget(ch[ch_num])
    while abs(dT)>2*dead_band:
        RE(sleep(min([abs(dtime)*60,60])))        # get an update after max 1 minute...
        dtime=(T_set-caget(ch[ch_num]))/(abs(get_T_gradient(channel))+.1)
        dT=T_set-caget(ch[ch_num])  #why was this commented??
        print(time.ctime()+ '       updated estimate to reach T='+str(T_set)[:5]+'C on channel '+caget('XF:11IDB-ES{Env:01-Out:1}Out-Sel','char')+': '+str(dtime)[:5]+' minutes    current temperature: '+str(caget(ch[ch_num]))[:5]+'C')
    print('hurray! temperature within 2x deadband! Going to check for stability....waiting max 1x wait_time to stabilize + 1x wait_time!')
    check=0
    period=0    
    while check<10 and period<5:
        if get_T_stability(wait_time,channel, dead_band) ==1:
            period=period+1
        elif get_T_stability(wait_time,channel, dead_band) ==0:
            period=0
        check=check+1
    if period == 5:
        message=time.ctime()+'    achieved T='+str(T_set)+' +/- '+str(dead_band)+'C for '+str(wait_time)+'s'
    elif period<5 and check==10:
        message=time.ctime()+'    failed to achieve T='+str(T_set)+' +/- '+str(dead_band)+'C for '+str(wait_time)+'s, required stability achieved for ~'+str(period*wait_time/5)+'s only'
    print(message)
    if log_entry=='on':
        olog_entry(message)
    else: pass
        

def get_T_stability(wait_time,channel,dead_band):
    """
    checks whether the temperatures is within the deadband for 1/5 of the total waiting time
    -> yes: returns 1 | no: returns 0
    """
    ch=['none','XF:11IDB-ES{Env:01-Chan:A}T:C-I','XF:11IDB-ES{Env:01-Chan:B}T:C-I','XF:11IDB-ES{Env:01-Chan:C}T:C-I','XF:11IDB-ES{Env:01-Chan:D}T:C-I']
    ch_num=caget('XF:11IDB-ES{Env:01-Out:'+str(channel)+'}Out-Sel')
    if int(wait_time/5) >=1:
      temperatures=np.zeros(int(wait_time/5))
      for i in range(int(wait_time/5)):
        RE(sleep(1))
        temperatures[i]=caget(ch[ch_num])-(caget('XF:11IDB-ES{Env:01-Out:'+str(channel)+'}T-SP') - 273.15)
        if max(abs(temperatures))>dead_band:
          T_stability_pass=0
        elif max(abs(temperatures))<=dead_band:
          T_stability_pass=1
    else:
        RE(sleep(1))
        temperatures=caget(ch[ch_num])-(caget('XF:11IDB-ES{Env:01-Out:'+str(channel)+'}T-SP') - 273.15)
        print(temperatures)
        if temperatures>dead_band:
          T_stability_pass=0
        elif temperatures<=dead_band:
          T_stability_pass=1
    return T_stability_pass
    
    
def get_T_gradient(channel):
    """
    returns temperature gradient on control channel in deg.C/min
    """
    ch=['none','XF:11IDB-ES{Env:01-Chan:A}T:C-I','XF:11IDB-ES{Env:01-Chan:B}T:C-I','XF:11IDB-ES{Env:01-Chan:C}T:C-I','XF:11IDB-ES{Env:01-Chan:D}T:C-I']
    ch_num=caget('XF:11IDB-ES{Env:01-Out:'+str(channel)+'}Out-Sel')    
    T1=caget(ch[ch_num])
    t1=time.time()
    RE(sleep(60))
    T2=caget(ch[ch_num])
    t2=time.time()
    T_gradient=60*abs(T2-T1)/(t2-t1)
    return T_gradient

def olog_entry(string):
    """
    wrapper for making an olog entry within a 'try / except: pass' sequence, to avoid hanging up, in case olog is not reachable
    calling sequence: olog_entry(string)
    """
    try:
        olog_client.log(string)
    except:
        print("Warning: olog entry has faild.."+string)
        pass
# automatic purging procedure for cryo-cooler:
def purge_cryo():
    """
    automatically purge cryo-cooler according to Bruker manual
    pre-requisit: GN2 of 1.5<p<3.0 bar connected to V21 
    AND cryo-control NOT disabled, e.g. by EPS
    calling sequence: purge_cryo()
    LW 05/27/2018
    """
    print('start purging cryo-cooler')
    print('Please make sure: \n 1) GN2 of 1.5<p<3.0 bar connected to V21 \n 2) cryo-control NOT disabled, e.g. by EPS')
    print('going to check EPS status:')
    if caget('XF:11IDA-OP{Cryo:1}Enbl-Sts') == 1:
        print('cryo-cooler operations are enabled!')
    else: raise cryo_Exception('error: cryo-cooler operations not enabled by EPS')
    print('going to close all valves....')
    caput('XF:11IDA-UT{Cryo:1-IV:21}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:09}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:19}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:15}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:20}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:10}Pos-SP',0)
    caput('XF:11IDA-UT{Cryo:1-IV:11}Pos-SP',0)
    caput('XF:11IDA-UT{Cryo:1-IV:17_35}Cmd:Cls-Cmd',1) #V17.2
    caput('XF:11IDA-UT{Cryo:1-IV:17_100}Cmd:Cls-Cmd',1)  #V17.1
    print('purging step 1/3, taking 30 min \n current time: '+str(datetime.now()))
    caput('XF:11IDA-UT{Cryo:1-IV:20}Cmd:Opn-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:09}Cmd:Opn-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:10}Pos-SP',100)
    caput('XF:11IDA-UT{Cryo:1-IV:21}Cmd:Opn-Cmd',1)
    for i in range(6):
        print('time left on purging step 1/3: '+str(30-i*5)+'min \n')
        RE(sleep(300))
    print('purging step 1/3 complete....proceeding to 2/3!')
    caput('XF:11IDA-UT{Cryo:1-IV:09}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:11}Pos-SP',100)
    print('purging step 2/3, taking 15 min \n current time: '+str(datetime.now()))
    for i in range(3):
       print('time left on purging step 2/3: '+str(15-i*5)+'min \n')
       RE(sleep(300))
    print('purging step 2/3 complete....proceeding to 3/3!')
    caput('XF:11IDA-UT{Cryo:1-IV:11}Pos-SP',0)
    caput('XF:11IDA-UT{Cryo:1-IV:17_35}Cmd:Opn-Cmd',1) 
    caput('XF:11IDA-UT{Cryo:1-IV:17_100}Cmd:Opn-Cmd',1)
    print('purging step 3/3, taking 15 min \n current time: '+str(datetime.now()))
    for i in range(3):
       print('time left on purging step 3/3: '+str(15-i*5)+'min \n')
       RE(sleep(300))
    print('purging COMPLETE! Closing all valves...')
    caput('XF:11IDA-UT{Cryo:1-IV:21}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:17_35}Cmd:Cls-Cmd',1) 
    caput('XF:11IDA-UT{Cryo:1-IV:17_100}Cmd:Cls-Cmd',1)
    caput('XF:11IDA-UT{Cryo:1-IV:10}Pos-SP',0)
    caput('XF:11IDA-UT{Cryo:1-IV:20}Cmd:Cls-Cmd',1)


    

class cryo_Exception(Exception):
    pass

# Lutz's test Nov 08 end

# begin test better function to check if beam is available for experiment + better recovery [Jan 2017]
def check_ring():
    if caget('SR-OPS{}Mode-Sts',1) == 'Operations' and caget('SR:C11-EPS{PLC:1}Sts:ID_BE_Enbl-Sts') ==1 and caget('SR:C03-BI{DCCT:1}I:Real-I') >180:
        ring_ok=1
        print('checking for SR ring status...seems ok')
    else:
        ring_ok=0
        print('checking for SR ring status...seems there is a problem')        
    return ring_ok

def wait_for_ring(wait_after=0):
    ring_ok=check_ring()
    if ring_ok==0:
        while ring_ok==0:
            print('no beam in SR ring...checking again in 5 minutes.')
            RE(sleep(300))
            ring_ok=check_ring()
        RE(sleep(wait_after))
    if ring_ok==1: pass

def check_bl():
    """
    macro to check whether stable beam can be obtained on the DBPM
    opens all shutters, checks whether beam is blocked by diode
    checks for feedback stays on (-> enough intensity on DBPM)
    checks for feedback running (-> deviation of <.5um combined error in X & Y in slow readout)
    """
    print('checking beamline for beam available...')
    #diode_IN() 
    att2.set_T(0) 
    fe_sh.open()
    foe_sh.open()
    fast_sh.open()
    current_T=att.get_T()
    att.set_T(1)
    time.sleep(2)

    #expected_feedback_voltage_A=3.67    # Dont't drive the beamline into the wall!!!
    #expected_feedback_voltage_B=4.91

    #if abs(caget('XF:11IDB-BI{XBPM:02}CtrlDAC:ALevel-I')-expected_feedback_voltage_A)>0.4:
    #   print('Feedback voltage A seems wrong, setting it to '+str(expected_feedback_voltage_A))
    #    caput('XF:11IDB-BI{XBPM:02}CtrlDAC:ALevel-SP',expected_feedback_voltage_A)
    #if abs(caget('XF:11IDB-BI{XBPM:02}CtrlDAC:BLevel-I')-expected_feedback_voltage_B)>0.4:
    #   print('Feedback voltage B seems wrong, setting it to '+str(expected_feedback_voltage_B))
    #    caput('XF:11IDB-BI{XBPM:02}CtrlDAC:BLevel-SP',expected_feedback_voltage_B)
    
    time.sleep(2) 

    RE(feedback_ON())
    time.sleep(2)
    if caget('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP')==1 and caget('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP')==1 and abs(caget('XF:11IDB-BI{XBPM:02}Pos:X-I'))+abs(caget('XF:11IDB-BI{XBPM:02}Pos:Y-I'))<.8:
        bl_ok=1
        print('################################\n')
        print('checked beamline: beam on DBPM, all ok!')
    else:
        bl_ok=0
        print('################################\n')
        print('checked beamline: NO beam on DBPM, not ready for experiment....')
    att.set_T(current_T)
    print('Setting back transmission to '+str(current_T))
    return bl_ok

def check_recover():
    print('checking SR ring and BL for beam available and try to recover if necessary....')
    ring_ok=check_ring()
    if ring_ok==1:
        pass
    elif ring_ok==0:
        print('looks like a beam loss in the SR ring...')
        try:
            olog_client.log('looks like a beam loss in the SR ring...trying to recover')
        except: pass    
        wait_for_ring()
    bl_ok=check_bl()
    #bl_ok=check_bl() # let's check a second time ...?!
    if bl_ok==1:
        pass
    elif bl_ok==0:
        print('beam in SR, but not at DBPM...trying to recover...')
        try:
            olog_client.log('beam in SR, but not at DBPM...trying to recover...')
        except: pass    
        caput('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP',0)    # DBPM feedback off
        caput('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP',0)
        caput('XF:11IDA-OP{Mir:HDM-Ax:P}Sts:FB-Sel',1) # Epics feedback on HDM on
        RE(sleep(8))
        if abs(caget('XF:11IDA-OP{Mir:HDM-Ax:P}PID-SP')-caget('XF:11IDA-OP{Mir:HDM-Ax:P}Pos-I'))>.5:
            print('Beam in Storage ring, but cannot recover at BL side...')
            try:
                olog_client.log('Beam in Storage ring, but cannot recover at BL side...possible problem wiht PID loop on SIEPA3P')
            except: pass    
            raise check_Exception('error: looks like the PID loop on SIEPA3P is NOT running, abort recovery attempt')
        else: pass
        caput('XF:11IDB-BI{XBPM:02}CtrlDAC:BLevel-SP',caget('XF:11IDB-BI{XBPM:02}CtrlDAC:BLevel-SP')) 
                # enforce last known (good) DAC outputs
        caput('XF:11IDB-BI{XBPM:02}CtrlDAC:ALevel-SP',caget('XF:11IDB-BI{XBPM:02}CtrlDAC:ALevel-SP'))
        caput('XF:11IDB-BI{XBPM:02}Fdbk:BEn-SP',1)
        RE(sleep(10))
        caput('XF:11IDA-OP{Mir:HDM-Ax:P}Sts:FB-Sel',0)
        caput('XF:11IDB-BI{XBPM:02}Fdbk:AEn-SP',1)            # back to feedback on DBPM
        RE(sleep(10))
        bl_ok=check_bl()
        if bl_ok==0:
            feedback_ON()    # one last chance...
        else: pass
        bl_ok=check_bl()
        if bl_ok==1:
            print('Successfully recovered! Hurray!')
            try:
                olog_client.log('Successfully recoverd beam loss. Check data for impact of possible non-ideal alignment.')
            except: 
                pass    
        elif bl_ok==0:
            try:
                olog_client.log('Beam in Storage ring, but cannot recover at BL side...abort recovery attempt')
            except: pass    
            raise check_Exception('error: could not recover beam on BL side...abort!')

    
class check_Exception(Exception):
    pass
    """
    class to raise exceptions during beamline auto-check and recovery
    """

# end test better function to check if beam is available for experiment + better recovery

def check_cryo(level_threshold=55.):
    """
    checking whether cryo-cooler refill is in progress or initiating refill, if current level is below threshold.
    waits for refill to be completed and reports current filling level
    calling sequence: check_cryo(level_threshold=55.)
    """
    if caget('XF:11IDA-UT{Cryo:1}L:19-I')<level_threshold or caget('XF:11IDA-UT{Cryo:1-IV:19}Pos-I') >10.:
        if caget('XF:11IDA-UT{Cryo:1-IV:19}Pos-I') >10.:
            print('cryo-cooler refill in progress, wait for completion. Current filling level: '+ str(caget('XF:11IDA-UT{Cryo:1}L:19-I'))[:5]+'%')
        elif caget('XF:11IDA-UT{Cryo:1}L:19-I')<level_threshold and caget('XF:11IDA-UT{Cryo:1-IV:19}Pos-I') <10.:
            print('cryo-cooler level: '+ str(caget('XF:11IDA-UT{Cryo:1}L:19-I'))[:5]+'% -> going to refill cryo_cooler')
        else: pass
        caput('XF:11IDA-UT{Cryo:1-IV:19}Pos-SP',100)
        refill_on=1
        #print('cryo-cooler level: '+ str(caget('XF:11IDA-UT{Cryo:1}L:19-I'))+'-> going to refill cryo_cooler')
        while refill_on==1:
            RE(sleep(60))
            if caget('XF:11IDA-UT{Cryo:1-IV:19}Pos-I') >10.:
                print('cryo-cooler refill in progress, filling level: '+str(caget('XF:11IDA-UT{Cryo:1}L:19-I'))[:5])
            elif caget('XF:11IDA-UT{Cryo:1-IV:19}Pos-I') <10.:
                print('cryo-cooler refill complete!')
                refill_on=0
    else:
        print('cryo-cooler level: '+ str(caget('XF:11IDA-UT{Cryo:1}L:19-I'))[:5]+'-> no refill at this time')

# reference position horz kinoform lens 1 (horz focus for SAXS), 9.65 keV 05/29/2017
def kinoform_focus(foc='horz_SAXS_9650'):
    if foc ==     'horz_SAXS_9650':
        RE(mv([k1.z,k1.x,k1.y,k1.chi,k1.theta,k1.phi,k1.lx,k1.ly],[5.,-.0524,2.146,2.0,-.25,1.52,.768,7.016]))
    if foc ==     'vert_WAXS_9750':
        mov([k1.z,k1.x,k1.y,k1.chi,k1.theta,k1.phi,k1.lx,k1.ly],[-20.,4.95,-3.167,2.0,-.98,-.68,9.244,3.93])
    if foc ==     'vert_WAXS_12800':
        RE(mv([k1.z,k1.x,k1.y,k1.chi,k1.theta,k1.phi,k1.lx,k1.ly],[0.,4.55,-3.167,2.65,.2,-.68,9.098,4.916]))
    if foc ==     'horz_WAXS_12800':
        mov([k2.z,k2.x,k2.y,k2.chi,k2.theta,k2.phi,k2.lx,k2.ly],[0.,0.002,4.6,.2,-1.24,-2.,-.868,6.975])
    if foc ==     'horz_WAXS_9750':
        mov([k2.z,k2.x,k2.y,k2.chi,k2.theta,k2.phi,k2.lx,k2.ly],[0.,-.44,4.6,.2,-1.24,-2.,-.868,7.049])

def create_mv_list(list_positioner, list_positions):
	mv_list = []
	for i in range(len(list_positioner)):
		mv_list.append(list_positioner[i])
		mv_list.append(list_positions[i])
	return mv_list

def kinoform_position(foc='horz_SAXS_9650'):
	"""
	move kinoform to set of positions, depending on desired focus
	!!! positions need to be updated regularly!!! -> check optical image in case of doubt
	available sets of positions: 
	horz_SAXS_9650
	vert_WAXS_9750
	vert_WAXS_12800
	horz_WAXS_12800
	horz_WAXS_9750
	"""
	positioner_kl1 = [k1.z,k1.x,k1.y,k1.chi,k1.theta,k1.phi,k1.lx,k1.ly]
	positioner_kl2 = [k2.z,k2.x,k2.y,k2.chi,k2.theta,k2.phi,k2.lx,k2.ly]
	pos_horz_SAXS_9650 = [5.,-.0524,1.8324,2.0,-.25,1.52,.768,7.016]
	pos_vert_WAXS_9750 = [-20.,4.95,-3.167,2.0,-.98,-.68,9.244,3.93]
	pos_vert_WAXS_12800 = [0.,4.55,-3.167,2.65,.2,-.68,9.098,4.916]
	pos_horz_SAXS_12800 = [0.,0.002,4.6,.2,-1.24,-2.,-.868,6.975]
	pos_horz_WAXS_9750 = [0.,-.44,4.6,.2,-1.24,-2.,-.868,7.049]
	if foc == 'horz_SAXS_9650':
		mv_list = create_mv_list(positioner_kl1,pos_horz_SAXS_9650)
	if foc == 'vert_WAXS_9750':
		mv_list = create_mv_list(positioner_kl1,pos_vert_WAXS_9750)
	if foc == 'vert_WAXS_12800':
		mv_list = create_mv_list(positioner_kl1,pos_vert_WAXS_12800)
	if foc == 'horz_WAXS_12800':
		mv_list = create_mv_list(positioner_kl2,pos_horz_WAXS_12800)
	if foc ==     'horz_WAXS_9750':
		mv_list = create_mv_list(positioner_kl2,pos_horz_WAXS_9750)
	RE(mv(*(mv_list)))

#def movr_samx(value):
#    movr(diff.xh,-value)
#    movr(diff.xv2,-value)


### python based kinematics for rotation of SAXS table's WAXS section #### 03/08/2017
# WAXS section rotation
def WAXS_rot_setup():          
    WAXS_angle=np.arange(0,17.2,.2)
    x1_pos= 1399*2*np.pi/360.*WAXS_angle
    x2_pos=5144.23*np.sin((WAXS_angle-4.008)/180*np.pi)+359.56
    x2_velocity=np.array([3.669,3.669,3.669,3.67,3.671,3.672,3.672,3.673,3.674,3.674,3.675,3.675,3.675,3.676,3.676,3.676,3.677,3.677,3.677,3.677,3.677,3.677,3.677,3.677,3.677,3.677,3.676,3.676,3.676,3.675,3.675,3.675,3.674,3.674,3.673,3.672,3.672,3.671,3.67,3.669,3.669,3.668,3.667,3.666,3.665,3.664,3.663,3.661,3.66,3.659,3.658,3.656,3.655,3.653,3.652,3.651,3.649,3.647,3.646,3.644,3.642,3.64,3.639,3.637,3.635,3.633,3.631,3.629,3.627,3.625,3.622,3.62,3.618,3.616,3.613,3.611,3.608,3.606,3.603,3.601,3.598,3.595,3.593,3.59,3.587,3.584])
    return [WAXS_angle,x1_pos,x2_pos,x2_velocity]

def WAXS_rot_pos():
    '''
    calculates current rotation angle for SAXS table's WAXS section from X1 and X2 positions via a look-up table
    '''
    [WAXS_angle,x1_pos,x2_pos,x2_velocity]=WAXS_rot_setup()
    WAXS_angle=np.array(WAXS_angle)
    x1_pos=np.array(x1_pos)
    x2_pos=np.array(x2_pos)
    x2_velocity=np.array(x2_velocity)
    ### WAXS angle according to X1:    
    if SAXS_x1.position >415.09 or SAXS_x1.position <=-.2:
        raise rotation_exception('error: position of X1 is out of range')    
    elif SAXS_x1.position <0:
        WAXS_angle_x1=0
    elif SAXS_x1.position <415.09 and SAXS_x1.position >=0:
        WAXS_angle_x1 = np.interp(SAXS_x1.position,x1_pos,WAXS_angle)
    ### WAXS angle according to X2:    
    if SAXS_x2.position >1516.06 or SAXS_x1.position <=-.2:
        raise rotation_exception('error: position of X2 is out of range')    
    elif SAXS_x2.position <0:
        WAXS_angle_x2=0
    elif SAXS_x2.position <1516.06 and SAXS_x2.position >=0:
        WAXS_angle_x2 = np.interp(SAXS_x2.position,x2_pos,WAXS_angle)
    curr_WAXS_angle=0.5*(WAXS_angle_x1+WAXS_angle_x2)
    print('WAXS rotation according to X1: '+str(WAXS_angle_x1)+'  WAXS rotation according to X2: '+str(WAXS_angle_x2)+'  -> WAXS rotation: ~'+str(curr_WAXS_angle))
    return curr_WAXS_angle

def WAXS_rotation(angle):
    '''
    moves SAXS table's WAXS section to desired rotation angle in 2 deg steps, using lookup table for positions and X2 velocity
    WAXS_rotation(angle) -> angle [deg.]
    checks that 470 < z2 < 500 & z1<20 
    '''
    max_angle=14.1 #hard coded limit for current setup    
    [WAXS_angle,x1_pos,x2_pos,x2_velocity]=WAXS_rot_setup()
    WAXS_angle=np.array(WAXS_angle)
    x1_pos=np.array(x1_pos)
    x2_pos=np.array(x2_pos)
    x2_velocity=np.array(x2_velocity)
    if angle <0 or angle>max_angle:
        raise rotation_exception('error: requested rotation angle out of range')
    curr_WAXS_angle=WAXS_rot_pos()
    #curr_WAXS_angle=7.9 ### fake for test
    if angle >= curr_WAXS_angle:
        direction=1
    elif angle < curr_WAXS_angle:
        direction=-1
    print('going to move WAXS section from '+str(curr_WAXS_angle)+' to: '+str(angle))
    while abs(angle - curr_WAXS_angle) > 1:        # moving in 1 deg steps
        z2=caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z2}Mtr.RBV')
        z1=caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z1}Mtr.RBV')
        if z2>470 and z2<500 and z1<20:
            curr_velocity= np.interp((curr_WAXS_angle+direction*.5),WAXS_angle,x2_velocity)
            curr_X1=np.interp((curr_WAXS_angle+direction*1),WAXS_angle,x1_pos)
            curr_X2=np.interp((curr_WAXS_angle+direction*1),WAXS_angle,x2_pos)
            print('moving to: '+str(curr_WAXS_angle+direction*1)+' setting X2 velocity to '+str(curr_velocity)+'  X1 -> '+str(curr_X1)+'  X2 -> '+str(curr_X2))
            # need to do the actual moves here:
            SAXS_x2.velocity.value=curr_velocity
            RE(mv(SAXS_x1,curr_X1,SAXS_x2,curr_X2))
            #mov([SAXS_x1,SAXS_x2],[curr_X1,curr_X2])
            curr_WAXS_angle=WAXS_rot_pos()        # the real thing...
            #curr_WAXS_angle=curr_WAXS_angle+direction*1 #faking move for testing
        else:
            raise Exception('ERROR: need 470 < z2 < 500 & z1<20 to do rotation')
    # moving the balance:
    if abs(angle - curr_WAXS_angle) <1.2:
        z2=caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z2}Mtr.RBV')
        z1=caget('XF:11IDB-ES{Tbl:SAXS-Ax:Z1}Mtr.RBV')
        if z2>470 and z2<500 and z1<20:
            curr_X1=np.interp(angle,WAXS_angle,x1_pos)
            curr_X2=np.interp(angle,WAXS_angle,x2_pos)
            print('moving to: '+str(angle)+'  X1 -> '+str(curr_X1)+'  X2 -> '+str(curr_X2))    
            # need to do the actual move here:
            #mov([SAXS_x1,SAXS_x2],[curr_X1,curr_X2])
            RE(mv(SAXS_x1,curr_X1,SAXS_x2,curr_X2))
        else:
            raise Exception('ERROR: need 470 < z2 < 500 & z1<20 to do rotation')
    else: raise rotation_exception('error: discrepancy from where the rotation is expected to be....')


class rotation_exception(Exception):
    pass
    
#def wait_for_pv(dets, ready_signal, md=None):
#    if md is None:
#        md = {}
#    def still_waiting():
#        return ready_signal.value != 1
#        
#    def wait_for_motor_to_cross_threshold():
#        return motor.postion < threshold

#    @bpp.stage_decorator(dets)
#    @bpp.run_decorator(md=md)
#    def inner():

#        while still_waiting():
#            yield from bps.sleep(.1)
#        yield from bps.trigger_and_read(dets)
        
#    yield from inner()

#def wait_for_motor(dets, motor, md=None):
#    if md is None:
#        md = {}
        
#    def still_waiting():
#        return motor.postion < threshold

#    @bpp.stage_decorator(dets)
#    @bpp.run_decorator(md=md)
#    def inner():

#        while still_waiting():
#            yield from bps.sleep(.1)
#        yield from bps.trigger_and_read(dets)
        
#    yield from inner()

#Amplifier stage - J.Lhermitte et al.
#amp_x = EpicsMotor('XF:11IDB-OP{BS:Samp-Ax:X}Mtr', name='amp_x')
#amp_y = EpicsMotor('XF:11IDB-OP{Stg:Samp-Ax:Phi}Mtr', name='amp_y')
#amp_z = EpicsMotor('XF:11IDB-OP{BS:Samp-Ax:Y}Mtr', name='amp_z')


### ES sample vacuum pump macros

gn2_close = 'XF:11IDB-ES{Sample-AV:GN2}Cmd:Cls-Cmd'
gn2_open = 'XF:11IDB-ES{Sample-AV:GN2}Cmd:Opn-Cmd'
tgv_open = 'XF:11IDB-ES{Sample-GV:Turbo}Cmd:Opn-Cmd'
tgv_close = 'XF:11IDB-ES{Sample-GV:Turbo}Cmd:Cls-Cmd'
cryo_close = 'XF:11IDB-ES{Sample-GV:Cryo}Cmd:Cls-Cmd' 

turbo_on = 'XF:11IDB-ES{SampleVacuum}TurboEnable'
pump_on = 'XF:11IDB-ES{SampleVacuum}BackingEnable'

vac_pv = 'XF:11IDB-VA{Samp:1-TCG:1}P-I'
T_pv = 'XF:11IDB-ES{Env:01-Chan:C}T:C-I'
T_A = 'XF:11IDB-ES{Env:01-Chan:A}T:C-I'
T_min = 15

T_thresh = 85

def auto_pump():
    '''
    auto_pump() - pumps down the sample chamber
    - makes sure pumps are stopped (wait time of 60 s..)
    - 
    '''
    if caget(vac_pv) >=640:
        caput(gn2_close,1)
        caput(turbo_on,0)
        caput(pump_on,0)
        print('making sure pumps are stopped...')
        RE(sleep(60))
        if caget(turbo_on) ==0 and caget(pump_on) == 0:
            caput(tgv_open,1)
            caput(pump_on,1)
            print('waiting for pressure to be ok so start turbo')
            ready_for_turbo=False
            while not ready_for_turbo:
                RE(sleep(3))
                if caget(vac_pv) < 5:
                    ready_for_turbo = True
            caput(turbo_on,1)
            print('all steps for pump-down completed!')
    else:
        raise Exception('chamber not at atmospheric pressure...')


def auto_vent():
    if caget(T_pv) < T_thresh:
    #if caget(T_A) > T_min:
        #turning off the cryo GV 
        caput(cryo_close,1)
        caput(tgv_close,1)
        caput(turbo_on,0)
        RE(sleep(10))
        caput(pump_on,0)
        caput(gn2_open,1)
        vent_complete=False
        while not vent_complete:
            RE(sleep(.5))
            if caget(vac_pv) >= 670:
                vent_complete=True
        caput(gn2_close,1)
        print('venting procedure complete!')
    else:
        raise Exception('temperature needs to be below %sC to vent!'%T_thresh) 
