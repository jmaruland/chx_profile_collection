from contextlib import nullcontext
import time as ttime  # tea time
from types import SimpleNamespace
from datetime import datetime
from ophyd import (ProsilicaDetector, SingleTrigger, TIFFPlugin,
                   ImagePlugin, StatsPlugin, DetectorBase, HDF5Plugin,
                   AreaDetector, EpicsSignal, EpicsSignalRO, ROIPlugin,
                   TransformPlugin, ProcessPlugin, Device, DeviceStatus,
                   OverlayPlugin, ProsilicaDetectorCam)

from ophyd.status import StatusBase
from ophyd.device import Staged
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.base import ADComponent, EpicsSignalWithRBV
from ophyd.areadetector.filestore_mixins import (FileStoreTIFFIterativeWrite,
                                                 FileStoreHDF5IterativeWrite,
                                                 FileStoreBase, new_short_uid,
                                                 FileStoreIterativeWrite)
from ophyd import Component as Cpt, Signal
from ophyd.utils import set_and_wait
from pathlib import PurePath
from bluesky.plan_stubs import stage, unstage, open_run, close_run, trigger_and_read, pause
from collections import OrderedDict

from nslsii.ad33 import SingleTriggerV33, StatsPluginV33, CamV33Mixin

class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
    """Add this as a component to detectors that write TIFFs."""
    ## LUTZ THIS MAY BE BROKEN NUKE IF XRAY EYES DO NOT WORK
    def describe(self):
        ret = super().describe()
        key = self.parent._image_name
        color_mode = self.parent.cam.color_mode.get(as_string=True)
        if color_mode == 'Mono':
            ret[key]['shape'] = [
                self.parent.cam.num_images.get(),
                self.array_size.height.get(),
                self.array_size.width.get()
                ]

        elif color_mode in ['RGB1', 'Bayer']:
            ret[key]['shape'] = [self.parent.cam.num_images.get(), *self.array_size.get()]
        else:
            raise RuntimeError("SHould never be here")

        cam_dtype = self.parent.cam.data_type.get(as_string=True)
        type_map = {'UInt8': '|u1', 'UInt16': '<u2', 'Float32':'<f4', "Float64":'<f8'}
        if cam_dtype in type_map:
            ret[key].setdefault('dtype_str', type_map[cam_dtype])


        return ret


class TIFFPluginEnsuredOff(TIFFPlugin):
    """Add this as a component to detectors that do not write TIFFs."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([('auto_save', 'No')])

class ProsilicaDetectorCamV33(ProsilicaDetectorCam):
    '''This is used to update the Standard Prosilica to AD33. It adds the
process
    '''
    wait_for_plugins = Cpt(EpicsSignal, 'WaitForPlugins',
                           string=True, kind='config')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['wait_for_plugins'] = 'Yes'

    def ensure_nonblocking(self):
        self.stage_sigs['wait_for_plugins'] = 'Yes'
        for c in self.parent.component_names:
            cpt = getattr(self.parent, c)
            if cpt is self:
                continue
            if hasattr(cpt, 'ensure_nonblocking'):
                cpt.ensure_nonblocking()

class StandardProsilica(SingleTrigger, ProsilicaDetector):
    image = Cpt(ImagePlugin, 'image1:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    trans1 = Cpt(TransformPlugin, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    over1 = Cpt(OverlayPlugin, 'Over1:')

    # This class does not save TIFFs. We make it aware of the TIFF plugin
    # only so that it can ensure that the plugin is not auto-saving.
    tiff = Cpt(TIFFPluginEnsuredOff, suffix='TIFF1:')

    @property
    def hints(self):
        return {'fields': [self.stats1.total.name]}

class StandardProsilicaV33(SingleTriggerV33, ProsilicaDetector):
    cam = Cpt(ProsilicaDetectorCamV33, 'cam1:')
    image = Cpt(ImagePlugin, 'image1:')
    stats1 = Cpt(StatsPluginV33, 'Stats1:')
    stats2 = Cpt(StatsPluginV33, 'Stats2:')
    stats3 = Cpt(StatsPluginV33, 'Stats3:')
    stats4 = Cpt(StatsPluginV33, 'Stats4:')
    stats5 = Cpt(StatsPluginV33, 'Stats5:')
    trans1 = Cpt(TransformPlugin, 'Trans1:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    over1 = Cpt(OverlayPlugin, 'Over1:')

    # This class does not save TIFFs. We make it aware of the TIFF plugin
    # only so that it can ensure that the plugin is not auto-saving.
    tiff = Cpt(TIFFPluginEnsuredOff, suffix='TIFF1:')

    @property
    def hints(self):
        return {'fields': [self.stats1.total.name]}


class StandardProsilicaWithTIFF(StandardProsilica):
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/nsls2/data/chx/legacy/data/%Y/%m/%d/',
               root='/nsls2/data/chx/legacy/data')

class StandardProsilicaWithTIFFV33(StandardProsilicaV33):
    tiff = Cpt(TIFFPluginWithFileStore,
               suffix='TIFF1:',
               write_path_template='/nsls2/data/chx/legacy/data/%Y/%m/%d/',
               root='/nsls2/data/chx/legacy/data')
               #root='/XF11ID/data')

class EigerSimulatedFilePlugin(Device, FileStoreBase):
    sequence_id = ADComponent(EpicsSignalRO, 'SequenceId')
    file_path = ADComponent(EpicsSignalWithRBV, 'FilePath', string=True)
    file_write_name_pattern = ADComponent(EpicsSignalWithRBV, 'FWNamePattern',
                                          string=True)
    file_write_images_per_file = ADComponent(EpicsSignalWithRBV,
                                             'FWNImagesPerFile')
    current_run_start_uid = Cpt(Signal, value='', add_prefix=())
    enable = SimpleNamespace(get=lambda: True)

    def __init__(self, *args, **kwargs):
        self.sequence_id_offset = 1
        # This is changed for when a datum is a slice
        # also used by ophyd
        self.filestore_spec = "AD_EIGER2"
        self.frame_num = None
        super().__init__(*args, **kwargs)
        self._datum_kwargs_map = dict()  # store kwargs for each uid

    def stage(self):
        res_uid = new_short_uid()
        write_path = datetime.now().strftime(self.write_path_template)
        #set_and_wait(self.file_path, write_path + '/')
        self.file_path.set(write_path + '/').wait()
        #set_and_wait(self.file_write_name_pattern, '{}_$id'.format(res_uid))
        self.file_write_name_pattern.set('{}_$id'.format(res_uid)).wait()
        super().stage()
        fn = (PurePath(self.file_path.get()) / res_uid)
        ipf = int(self.file_write_images_per_file.get())
        # logger.debug("Inserting resource with filename %s", fn)
        self._fn = fn
        res_kwargs = {'images_per_file' : ipf}
        self._generate_resource(res_kwargs)

    def generate_datum(self, key, timestamp, datum_kwargs):
        # The detector keeps its own counter which is uses label HDF5
        # sub-files.  We access that counter via the sequence_id
        # signal and stash it in the datum.
        seq_id = int(self.sequence_id_offset) + int(self.sequence_id.get())  # det writes to the NEXT one
        datum_kwargs.update({'seq_id': seq_id})
        if self.frame_num is not None:
            datum_kwargs.update({'frame_num': self.frame_num})
        return super().generate_datum(key, timestamp, datum_kwargs)

    def describe(self,):
        ret = super().describe()
        if hasattr(self.parent.cam, 'bit_depth'):
            cur_bits = self.parent.cam.bit_depth.get()
            dtype_str_map = {8: '|u1', 16: '<u2', 32:'<u4'}
            ret[self.parent._image_name]['dtype_str'] = dtype_str_map[cur_bits]
        return ret


class EigerBase(AreaDetector):
    """
    Eiger, sans any triggering behavior.

    Use EigerSingleTrigger or EigerFastTrigger below.
    """
    num_triggers = ADComponent(EpicsSignalWithRBV, 'cam1:NumTriggers')
    file = Cpt(EigerSimulatedFilePlugin, suffix='cam1:',
               write_path_template='/PLACEHOLDER',
               root='/PLACEHOLDER')
    beam_center_x = ADComponent(EpicsSignalWithRBV, 'cam1:BeamX')
    beam_center_y = ADComponent(EpicsSignalWithRBV, 'cam1:BeamY')
    wavelength = ADComponent(EpicsSignalWithRBV, 'cam1:Wavelength')
    det_distance = ADComponent(EpicsSignalWithRBV, 'cam1:DetDist')
    threshold_energy = ADComponent(EpicsSignalWithRBV, 'cam1:ThresholdEnergy')
    photon_energy = ADComponent(EpicsSignalWithRBV, 'cam1:PhotonEnergy')
    manual_trigger = ADComponent(EpicsSignalWithRBV, 'cam1:ManualTrigger')  # the checkbox
    special_trigger_button = ADComponent(EpicsSignal, 'cam1:Trigger')  # the button next to 'Start' and 'Stop'
    image = Cpt(ImagePlugin, 'image1:')
    stats1 = Cpt(StatsPlugin, 'Stats1:')
    stats2 = Cpt(StatsPlugin, 'Stats2:')
    stats3 = Cpt(StatsPlugin, 'Stats3:')
    stats4 = Cpt(StatsPlugin, 'Stats4:')
    stats5 = Cpt(StatsPlugin, 'Stats5:')
    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')
    proc1 = Cpt(ProcessPlugin, 'Proc1:')

    shutter_mode = ADComponent(EpicsSignalWithRBV, 'cam1:ShutterMode')

    # hotfix: shadow non-existant PV
    size_link = None

    def stage(self, *args, **kwargs):
        # before parent
        ret = super().stage(*args, **kwargs)
        # after parent
        self.manual_trigger.set(1).wait()
        return ret

    def unstage(self):
        #set_and_wait(self.manual_trigger, 0)
        self.manual_trigger.set(0).wait()
        super().unstage()

    @property
    def hints(self):
        return {'fields': [self.stats1.total.name]}


class EigerDetectorCamV33(AreaDetectorCam):
    '''This is used to update the Eiger detector to AD33.
    '''
    firmware_version = Cpt(EpicsSignalRO, 'FirmwareVersion_RBV', kind='config')

    wait_for_plugins = Cpt(EpicsSignal, 'WaitForPlugins',
                           string=True, kind='config')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['wait_for_plugins'] = 'Yes'

    def ensure_nonblocking(self):
        self.stage_sigs['wait_for_plugins'] = 'Yes'
        for c in self.parent.component_names:
            cpt = getattr(self.parent, c)
            if cpt is self:
                continue
            if hasattr(cpt, 'ensure_nonblocking'):
                cpt.ensure_nonblocking()

class NewEigerDetectorCamV33(EigerDetectorCamV33):
    bit_depth = Cpt(EpicsSignalRO, 'BitDepthImage_RBV', kind='config')

class EigerBaseV33(EigerBase):
    cam = Cpt(EigerDetectorCamV33, 'cam1:')
    stats1 = Cpt(StatsPluginV33, 'Stats1:')
    stats2 = Cpt(StatsPluginV33, 'Stats2:')
    stats3 = Cpt(StatsPluginV33, 'Stats3:')
    stats4 = Cpt(StatsPluginV33, 'Stats4:')
    stats5 = Cpt(StatsPluginV33, 'Stats5:')


class EigerSingleTrigger(SingleTrigger, EigerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['cam.trigger_mode'] = 0
        self.stage_sigs['shutter_mode'] = 1  # 'EPICS PV'
        self.stage_sigs.update({'num_triggers': 1})

    def stage(self, *args, **kwargs):
        return super().stage(*args, **kwargs)

    def trigger(self, *args, **kwargs):
        status = super().trigger(*args, **kwargs)
        set_and_wait(self.special_trigger_button, 1)
        return status

    def read(self, *args, streaming=False, **kwargs):
        '''
            This is a test of using streaming read.
            Ideally, this should be handled by a new _stream_attrs property.
            For now, we just check for a streaming key in read and
            call super() if False, or read the one key we know we should read
            if True.

            Parameters
            ----------
            streaming : bool, optional
                whether to read streaming attrs or not
        '''
        #ret = super().read()
        #print("super read() : {}".format(ret))
        #return ret
        if streaming:
            key = self._image_name  # this comes from the SingleTrigger mixin
            read_dict = super().read()
            ret = OrderedDict({key: read_dict[key]})
            return ret
        else:
            ret = super().read(*args, **kwargs)
            return ret

    def describe(self, *args, streaming=False, **kwargs):
        '''
            This is a test of using streaming read.
            Ideally, this should be handled by a new _stream_attrs property.
            For now, we just check for a streaming key in read and
            call super() if False, or read the one key we know we should read
            if True.

            Parameters
            ----------
            streaming : bool, optional
                whether to read streaming attrs or not
        '''
        if streaming:
            key = self._image_name  # this comes from the SingleTrigger mixin
            read_dict = super().describe()
            ret = OrderedDict({key: read_dict[key]})
            return ret
        else:
            ret = super().describe(*args, **kwargs)
            return ret



class EigerSingleTrigger_AD37(SingleTrigger, EigerBaseV33):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['cam.trigger_mode'] = 0
        self.stage_sigs['shutter_mode'] = 1  # 'EPICS PV'
        self.stage_sigs.update({'num_triggers': 1})

    def stage(self, *args, **kwargs):
        return super().stage(*args, **kwargs)

    def trigger(self, *args, **kwargs):
        status = super().trigger(*args, **kwargs)
        #set_and_wait(self.special_trigger_button, 1)
        self.special_trigger_button.set(1).wait()
        return status

    def read(self, *args, streaming=False, **kwargs):
        '''
            This is a test of using streaming read.
            Ideally, this should be handled by a new _stream_attrs property.
            For now, we just check for a streaming key in read and
            call super() if False, or read the one key we know we should read
            if True.

            Parameters
            ----------
            streaming : bool, optional
                whether to read streaming attrs or not
        '''
        #ret = super().read()
        #print("super read() : {}".format(ret))
        #return ret
        if streaming:
            key = self._image_name  # this comes from the SingleTrigger mixin
            read_dict = super().read()
            ret = OrderedDict({key: read_dict[key]})
            return ret
        else:
            ret = super().read(*args, **kwargs)
            return ret

    def describe(self, *args, streaming=False, **kwargs):
        '''
            This is a test of using streaming read.
            Ideally, this should be handled by a new _stream_attrs property.
            For now, we just check for a streaming key in read and
            call super() if False, or read the one key we know we should read
            if True.

            Parameters
            ----------
            streaming : bool, optional
                whether to read streaming attrs or not
        '''
        if streaming:
            key = self._image_name  # this comes from the SingleTrigger mixin
            read_dict = super().describe()
            ret = OrderedDict({key: read_dict[key]})
            return ret
        else:
            ret = super().describe(*args, **kwargs)
            return ret

class EigerSingleTrigger_AD37_V2(EigerSingleTrigger_AD37):
    cam = Cpt(NewEigerDetectorCamV33, 'cam1:')

class FastShutterTrigger(Device):
    """This represents the fast trigger *device*.

    See below, FastTriggerMixin, which defines the trigging logic.
    """
    auto_shutter_mode = Cpt(EpicsSignal, 'Mode-Sts', write_pv='Mode-Cmd')
    num_images = Cpt(EpicsSignal, 'NumImages-SP')
    exposure_time = Cpt(EpicsSignal, 'ExposureTime-SP')
    acquire_period = Cpt(EpicsSignal, 'AcquirePeriod-SP')
    acquire = Cpt(EpicsSignal, 'Acquire-Cmd', trigger_value=1)


class EigerFastTrigger(EigerBase):
    tr = Cpt(FastShutterTrigger, '')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs['cam.trigger_mode'] = 3  # 'External Enable' mode
        self.stage_sigs['shutter_mode'] = 0  # 'EPICS PV'
        self.stage_sigs['tr.auto_shutter_mode'] = 1  # 'Enable'

    def trigger(self):
        self.dispatch('image', ttime.time())
        return self.tr.trigger()

class EigerManualTrigger(SingleTrigger, EigerBase):
    '''
        Like Eiger Single Trigger but the triggering is done through the
        special trigger button.
    '''
    def __init__(self, *args, **kwargs):
        self._set_st = None
        super().__init__(*args, **kwargs)
        # in this case, we don't need this + 1 sequence id cludge
        # this is because we write datum after image is acquired
        self.file.sequence_id_offset = 0
        self.file.filestore_spec = "AD_EIGER_SLICE"
        self.file.frame_num = 0
        # set up order
        self.stage_sigs = OrderedDict()
        self.stage_sigs['cam.image_mode'] = 1
        self.stage_sigs['cam.trigger_mode'] = 0
        self.stage_sigs['shutter_mode'] = 1
        self.stage_sigs['manual_trigger'] = 1
        #self.stage_sigs['cam.acquire'] = 1
        self.stage_sigs['num_triggers'] = 10

        # monkey patch
        # override with special trigger button, not acquire
        #self._acquisition_signal = self.special_trigger_button

    def stage(self):
        self.file.frame_num = 0
        super().stage()
        # for some reason if doing this too fast in staging
        # this gets reset. so I do it here instead.
        # the bit gets unset when done but we should unset again in unstage
        time.sleep(1)
        self.cam.acquire.put(1)
        # need another sleep to ensure the sequence ID is updated
        time.sleep(1)

    def unstage(self):
        self.file.frame_num = 0
        super().unstage()
        time.sleep(.1)
        self.cam.acquire.put(0)


    def trigger(self):
        ''' custom trigger for Eiger Manual'''
        if self._staged != Staged.yes:
            raise RuntimeError("This detector is not ready to trigger."
                               "Call the stage() method before triggering.")

        if self._set_st is not None:
            raise RuntimeError(f'trying to set {self.name}'
                               ' while a set is in progress')

        st = StatusBase()
        # idea : look at the array counter and the trigger value
        # the logic here is that I want to check when the status is back to zero
        def counter_cb(value, timestamp, **kwargs):
            # whenevr it counts just move on
            #print("changed : {}".format(value))
            self._set_st = None
            self.cam.array_counter.clear_sub(counter_cb)
            st._finished()


        # first subscribe a callback
        self.cam.array_counter.subscribe(counter_cb, run=False)

        # then call trigger on the PV
        self.special_trigger_button.put(1, wait=False)
        self.dispatch(self._image_name, ttime.time())
        self.file.frame_num += 1

        return st


# test_trig4M = FastShutterTrigger('XF:11IDB-ES{Trigger:Eig4M}', name='test_trig4M')


## This renaming should be reversed: no correspondance between CSS screens, PV names and ophyd....
xray_eye1 = StandardProsilicaV33('XF:11IDA-BI{Bpm:1-Cam:1}', name='xray_eye1')
xray_eye2 = StandardProsilicaV33('XF:11IDB-BI{Mon:1-Cam:1}', name='xray_eye2')
xray_eye3 = StandardProsilicaV33('XF:11IDB-BI{Cam:08}', name='xray_eye3')
xray_eye4 = StandardProsilicaV33('XF:11IDB-BI{Cam:09}', name='xray_eye4')
OAV = StandardProsilicaV33('XF:11IDB-BI{Cam:10}', name='OAV')  # beamline OAV using prosilica camera
#OAV = StandardProsilicaV33('XF:11ID-M3{Det-Cam:3}', name='OAV')  # printer OAV using Grasshoper UBS3 camera
#OAV.stage_sigs[OAV.cam.trigger_mode] = 'Off'


BCam =  StandardProsilicaV33('XF:11IDB-ES{BFLY-Cam:1}', name='BCam')
xray_eye1_writing = StandardProsilicaWithTIFFV33('XF:11IDA-BI{Bpm:1-Cam:1}', name='xray_eye1')
xray_eye2_writing = StandardProsilicaWithTIFFV33('XF:11IDB-BI{Mon:1-Cam:1}', name='xray_eye2')
xray_eye3_writing = StandardProsilicaWithTIFFV33('XF:11IDB-BI{Cam:08}', name='xray_eye3')
xray_eye4_writing = StandardProsilicaWithTIFFV33('XF:11IDB-BI{Cam:09}', name='xray_eye4')
OAV_writing = StandardProsilicaWithTIFFV33('XF:11IDB-BI{Cam:10}', name='OAV')   # beamline OAV using prosilica camera
#OAV_writing = StandardProsilicaWithTIFFV33('XF:11ID-M3{Det-Cam:3}', name='OAV') # printer OAV using Grasshoper UBS3 camera
OAV_writing.tiff.write_path_template = '/nsls2/data/chx/legacy/data/%Y/%m/%d/'
OAV_writing.tiff.read_path_template = '/nsls2/data/chx/legacy/data/%Y/%m/%d/'
OAV_writing.tiff.reg_root = '/nsls2/data/chx/legacy/data/'


BCam_writing =  StandardProsilicaWithTIFFV33('XF:11IDB-ES{BFLY-Cam:1}', name='BCam')
fs1 = StandardProsilicaV33('XF:11IDA-BI{FS:1-Cam:1}', name='fs1')
fs2 = StandardProsilicaV33('XF:11IDA-BI{FS:2-Cam:1}', name='fs2')
fs_wbs = StandardProsilicaV33('XF:11IDA-BI{BS:WB-Cam:1}', name='fs_wbs')
# dcm_cam = StandardProsilica('XF:11IDA-BI{Mono:DCM-Cam:1}', name='dcm_cam')
fs_pbs = StandardProsilicaV33('XF:11IDA-BI{BS:PB-Cam:1}', name='fs_pbs')
# elm = Elm('XF:11IDA-BI{AH401B}AH401B:',)

all_standard_pros = [xray_eye1, xray_eye2, xray_eye3, xray_eye4,
                     xray_eye1_writing, xray_eye2_writing,
                     xray_eye3_writing, xray_eye4_writing,
                     OAV, OAV_writing,
                     fs1, fs2,
                     fs_wbs, fs_pbs,    #BCam, BCam_writing,
                     ]
#                     xray_eye3_writing, fs1, fs2, dcm_cam, fs_wbs, fs_pbs]
for camera in all_standard_pros:
    camera.read_attrs = ['stats1', 'stats2', 'stats3', 'stats4', 'stats5']
    # camera.tiff.read_attrs = []  # leaving just the 'image'
    for stats_name in ['stats1', 'stats2', 'stats3', 'stats4', 'stats5']:
        stats_plugin = getattr(camera, stats_name)
        stats_plugin.read_attrs = ['total']
        #camera.stage_sigs[stats_plugin.blocking_callbacks] = 1

    #The following 2 lines should be used when not running AD V33
    #camera.stage_sigs[camera.roi1.blocking_callbacks] = 1
    #camera.stage_sigs[camera.trans1.blocking_callbacks] = 1

    #The following line should only be used when running AD V33
    camera.cam.ensure_nonblocking()
    #camera.stage_sigs[camera.cam.trigger_mode] = 'Fixed Rate'

#OAV.stage_sigs[OAV.cam.trigger_mode] = 'Off'
#OAV_writing.stage_sigs[OAV_writing.cam.trigger_mode] = 'Off'

for camera in [xray_eye1_writing, xray_eye2_writing, BCam_writing,
               xray_eye3_writing, xray_eye4_writing, OAV_writing]:
    camera.read_attrs.append('tiff')
    camera.tiff.read_attrs = []
    camera.cam.ensure_nonblocking()

def set_eiger_defaults(eiger):
    """Choose which attributes to read per-step (read_attrs) or
    per-run (configuration attrs)."""

    eiger.file.read_attrs = []
    eiger.read_attrs = ['file', 'stats1', 'stats2',
                        'stats3', 'stats4', 'stats5']
    for stats in [eiger.stats1, eiger.stats2, eiger.stats3,
                  eiger.stats4, eiger.stats5]:
        stats.read_attrs = ['total']
    eiger.configuration_attrs = ['beam_center_x', 'beam_center_y',
                                 'wavelength', 'det_distance', 'cam',
                                 'threshold_energy', 'photon_energy']
    eiger.cam.read_attrs = []
    eiger.cam.configuration_attrs = ['acquire_time', 'acquire_period',

                                     'num_images']
def no_plugins(det, *, skip_list=('file',)):
    """Disable all AD plugins we know about.

    This is a helper to disable all of the plugins on an area detector.
    The defaults are tune for eiger*m_single

    Parameters
    ----------
    det : AreaDetectorBase
        The device to opreate on

    skip_list : tuple[str], default=('file',)
        Any plugins to leave in their current state.
    """
    for p in det.component_names:
        if p in skip_list:
            continue
        plugin = getattr(det, p)
        if hasattr(plugin, 'disable_on_stage'):
            plugin.disable_on_stage()

def all_plugins(det, *, skip_list=()):
    """Enable all AD plugins we know about.

    This is a helper to enable all of the plugins on an area detector.

    Parameters
    ----------
    det : AreaDetectorBase
        The device to opreate on

    skip_list : tuple[str], default=()
        Any plugins to leave in their current state.
    """
    for p in det.component_names:
        if p in skip_list:
            continue
        plugin = getattr(det, p)
        if hasattr(plugin, 'enable_on_stage'):
            plugin.enable_on_stage()


def enable_plugins(det, plugin_names):
    """Selectively enable plugins on an AreaDetector

    Parameters
    ----------
    det : AreaDetectorBase
        The device to configure
    plugin_names : List[str]
        The plugins to enable
    """
    for p in plugin_names:
        getattr(det, p).enable_on_stage()

try:
    # Eiger 500k using internal trigger
    eiger500k_single = EigerSingleTrigger_AD37_V2('XF:11IDB-ES{Det:Eig500K}', name='eiger500K_single')
    set_eiger_defaults(eiger500k_single)
    # AD v3.3+ config:
    eiger500k_single.cam.ensure_nonblocking()
    eiger500k_single.file.write_path_template = '/nsls2/data/chx/assets/eiger500k/%Y/%m/%d/'
    eiger500k_single.file.reg_root ='/nsls2/data/chx/assets/eiger500k/'
except Exception:
    print('eiger500k not configured...')
    raise

# Eiger 1M using internal trigger
eiger1m_single = EigerSingleTrigger_AD37_V2('XF:11IDB-ES{Det:Eig1M}',
                                    name='eiger1m_single')
set_eiger_defaults(eiger1m_single)
# AD v3.3+ config:
eiger1m_single.cam.ensure_nonblocking()

# Eiger 4M using internal trigger
eiger4m_single = EigerSingleTrigger_AD37_V2('XF:11IDB-ES{Det:Eig4M}',
                                    name='eiger4m_single')
eiger4m_single.file.write_path_template = '/nsls2/data/chx/assets/eiger4m/%Y/%m/%d/'
eiger4m_single.file.reg_root ='/nsls2/data/chx/assets/eiger4m/'
set_eiger_defaults(eiger4m_single)
# AD v3.3+ config:
eiger4m_single.cam.ensure_nonblocking()

try:
    # Eiger 500K using fast trigger assembly
    eiger500k = EigerFastTrigger('XF:11IDB-ES{Det:Eig500K}', name='eiger500k')
    set_eiger_defaults(eiger500k)
    eiger500k.file.write_path_template = '/nsls2/data/chx/assets/eiger500k/%Y/%m/%d/'
    eiger500k.file.reg_root ='/nsls2/data/chx/assets/eiger500k/'
except Exception:
    print('eiger500k not configured...')

# Eiger 1M using fast trigger assembly
eiger1m = EigerFastTrigger('XF:11IDB-ES{Det:Eig1M}', name='eiger1m')
set_eiger_defaults(eiger1m)
eiger1m.file.write_path_template = '/nsls2/data/chx/assets/eiger1m/%Y/%m/%d/'
eiger1m.file.reg_root ='/nsls2/data/chx/assets/eiger1m/'

# Eiger 4M using fast trigger assembly
eiger4m = EigerFastTrigger('XF:11IDB-ES{Det:Eig4M}', name='eiger4m')
set_eiger_defaults(eiger4m)
eiger4m.file.write_path_template = '/nsls2/data/chx/assets/eiger4m/%Y/%m/%d/'
eiger4m.file.reg_root ='/nsls2/data/chx/assets/eiger4m/'

# setup manual eiger for 1d scans
# prototype
# trick: keep same epics name. This is fine
# if there are colliding keys, then we're doing something wrong
# (only one key name should be used)
eiger4m_manual = EigerManualTrigger('XF:11IDB-ES{Det:Eig4M}', name='eiger4m_single')
set_eiger_defaults(eiger4m_manual)
eiger4m_manual.file.write_path_template = '/nsls2/data/chx/assets/eiger4m/%Y/%m/%d/'
eiger4m_manual.file.reg_root ='/nsls2/data/chx/assets/eiger4m/'

eiger1m_manual = EigerManualTrigger('XF:11IDB-ES{Det:Eig1M}', name='eiger1m_single')
set_eiger_defaults(eiger1m_manual)
eiger1m_manual.file.write_path_template = '/nsls2/data/chx/assets/eiger1m/%Y/%m/%d/'
eiger1m_manual.file.reg_root ='/nsls2/data/chx/assets/eiger1m/'

try:
    eiger500k_manual = EigerManualTrigger('XF:11IDB-ES{Det:Eig500K}', name='eiger500k_single')
    set_eiger_defaults(eiger500k_manual)
    eiger500k_manual.file.write_path_template = '/nsls2/data/chx/assets/eiger500k/%Y/%m/%d/'
    eiger500k_manual.file.reg_root ='/nsls2/data/chx/assets/eiger500k/'
except Exception:
    print('eiger500k not configured...')

def dscan_manual(dets, motor, start, stop, num):
    for det in dets:
        det.stage_sigs.update({'num_triggers': num})

    yield from dscan(dets, motor, start, stop, num)

# from ophyd.sim import motor1
#RE(dscan_manual(eiger4m_manual, motor1, 0, 1, 10))
# this hangs because trigger() returns a self._status_type(self)
# which is a status object that never completes


def manual_count(det=eiger4m_single):
    detectors = [det]
    for det in detectors:
        yield from stage(det)
        yield from open_run()
        print("All slow setup code has been run. "
              "Type RE.resume() when ready to acquire.")
        yield from pause()
        yield from trigger_and_read(detectors)
        yield from close_run()
        for det in detectors:
            yield from unstage(det)


# Comment this out to suppress deluge of logging messages.
# import logging
# logging.basicConfig(level=logging.DEBUG)
# import ophyd.areadetector.filestore_mixins
# ophyd.areadetector.filestore_mixins.logger.setLevel(logging.DEBUG)
