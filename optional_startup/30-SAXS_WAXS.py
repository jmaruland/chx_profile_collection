from epics import caput,caget

scan_id_pv = 'XF:11ID-CT{ES:1}ai1'
scan_ID = EpicsSignal(scan_id_pv, name='scan_ID')

SAXS_done_pv='XF:11ID-CT{M3}bi3'
caget(BL_busy_pv)
caput('XF:11ID-CT{M3}bi3.DESC','SAXS done')
WAXS_done_pv='XF:11ID-CT{M3}bi4'
caget(BL_busy_pv)
caput('XF:11ID-CT{M3}bi4.DESC','WAXS done')

def mcount(detector_list,imnum=[1],exposure_time=[1],acquire_period=['auto']):
    """
    wrapper for multi-BlueSky session count: keep track of current scan_id as an EPICS PV that can be shared between BlueSky sessions
    can set individual number of images, exposure time and acquire period for a list of detectors
    TODO: check of input arguments for consistency and format, option for just keeping current settings on detectors
    """
    last_scan_id = int(max(scan_ID.get(),RE.md['scan_id']))
    yield from mv(scan_ID,last_scan_id+1)
    new_scan_id = int(last_scan_id+1)
    print('synchronizing BlueSky sessions: last scan ID: %s -> next scan ID: %s'%(last_scan_id,new_scan_id))
    RE.md['scan_id'] = last_scan_id
    
    # setting up the detectors:
    for ii,i in enumerate(detector_list):
        detector=i
        if acquire_period[ii] == 'auto':
            acquire_period[ii] = exposure_time[ii]
        i.cam.acquire_time.value=exposure_time[ii]       # setting up exposure for eiger500k/1m/4m_single
        i.cam.acquire_period.value=acquire_period[ii]
        i.cam.num_images.value=imnum[ii]
        if detector == pilatus800: # Pilatus doesn't seem to capture acquisition parameters in start document...
            RE.md['pil800k_exposure_time']=exposure_time[ii]
            RE.md['pil800k_acquire_period']=acquire_period[ii]
            RE.md['pil800k_imnum']=imnum[ii]

    yield from count(detector_list)
    
def mdscan(detectors, *args, num=None, per_step=None, md=None):
    """
    wrapper for multi-BlueSky session dscan: keep track of current scan_id as an EPICS PV that can be shared between BlueSky sessions
    """
    last_scan_id = int(max(scan_ID.get(),RE.md['scan_id']))
    yield from mv(scan_ID,last_scan_id+1)
    new_scan_id = int(last_scan_id+1)
    print('synchronizing BlueSky sessions: last scan ID: %s -> next scan ID: %s'%(last_scan_id,new_scan_id))
    RE.md['scan_id'] = last_scan_id
    yield from dscan(detectors, *args, num=None, per_step=None, md=None)
    
def mseries(det='eiger4m',shutter_mode='single',expt=.1,acqp='auto',imnum=5,comment='', feedback_on=False, PV_trigger=False, position_trigger=False ,analysis='', use_xbpm=False, OAV_mode='none',auto_compression=False,md_import={},auto_beam_position=True):
    """
    wrapper for multi-BlueSky session series: keep track of current scan_id as an EPICS PV that can be shared between BlueSky sessions
    """
    last_scan_id = int(max(scan_ID.get(),RE.md['scan_id']))
    RE(mv(scan_ID,last_scan_id+1))
    new_scan_id = int(last_scan_id+1)
    print('synchronizing BlueSky sessions: last scan ID: %s -> next scan ID: %s'%(last_scan_id,new_scan_id))
    RE.md['scan_id'] = last_scan_id
    series(det=det,shutter_mode=shutter_mode,expt=expt,acqp=acqp,imnum=imnum,comment=comment,feedback_on=feedback_on,PV_trigger=PV_trigger,position_trigger=position_trigger,analysis=analysis,use_xbpm=use_xbpm,OAV_mode=OAV_mode,auto_compression=auto_compression,md_import=md_import,auto_beam_position=auto_beam_position)
    
def triggered_WAXS(detector_list,imnum=[1],exposure_time=[1],acquire_period=['auto'],delay=0,comment=None,post_series=0):
    pil800k_shutter_mode(0)
    caput(WAXS_done_pv,0)
    trigger_signal_pv = 'XF:11ID-CT{M3}bi2' # printer setup   
    #trigger_signal_pv = 'XF:11ID-CT{ES:1}bi1'
    print('waiting for trigger signal....')
    while caget(trigger_signal_pv) <.5:
        RE(sleep(.5))
    RE(sleep(delay)) 
    RE(mcount(detector_list=detector_list,imnum=imnum,exposure_time=exposure_time,acquire_period=acquire_period),Measurement = comment)
    caput(trigger_signal_pv,0)
    RE(sleep(0.5))
    for p in range(post_series):
         #pil800k_shutter_mode(1)
         #att2.set_T(.19)
         if caget(SAXS_done_pv):
            RE(mvr(printer.x_bed,.1))
         RE(mcount([pilatus800],imnum=[100],exposure_time=[.1],acquire_period=[.105]))
    caput(WAXS_done_pv,1)
    pil800k_shutter_mode(1)
    caput('XF:11IDB-ES{Det:P800k}cam1:NumImages',1)
    if caget(SAXS_done_pv):
        fast_sh.close()

def WAXS_single_image():
    pil800k_shutter_mode(1)
    caput('XF:11IDB-ES{Det:P800k}cam1:NumImages',1)
    RE(mcount([pilatus800],exposure_time=[.1],acquire_period=[.15]))
    pil800k_shutter_mode(0)



def triggered_WAXS_continuous(detector_list,imnum=[1],exposure_time=[1],acquire_period=['auto'],delay=0,comment=None):
    while(True):
        triggered_WAXS(detector_list,imnum,exposure_time,acquire_period,delay,comment)
    

def pil800k_shutter_mode(mode):
    assert mode in [0,1] ,'mode must be 0 (no shutter) or 1 (EPICS signal)'
    caput('XF:11IDB-ES{Det:P800k}cam1:ShutterMode',mode)

    
    
    
    
    