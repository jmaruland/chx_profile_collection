# import time as ttime  # tea time
# from datetime import datetime
from ophyd import (
    ProsilicaDetector,
    SingleTrigger,
    TIFFPlugin,
    ImagePlugin,
    DetectorBase,
    HDF5Plugin,
    AreaDetector,
    EpicsSignal,
    EpicsSignalRO,
    ROIPlugin,
    TransformPlugin,
    ProcessPlugin,
    PilatusDetector,
    ProsilicaDetectorCam,
    PilatusDetectorCam,
    StatsPlugin,
)
from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.areadetector.base import ADComponent, EpicsSignalWithRBV
from ophyd.areadetector.filestore_mixins import FileStoreTIFFIterativeWrite
from ophyd import Component as Cpt, Signal
from ophyd.utils import set_and_wait
from nslsii.ad33 import SingleTriggerV33, StatsPluginV33

# import filestore.api as fs


# class TIFFPluginWithFileStore(TIFFPlugin, FileStoreTIFFIterativeWrite):
#     pass


# class ProsilicaDetectorCamV33(ProsilicaDetectorCam):
#     """This is used to update the standard prosilica to AD33."""

#     wait_for_plugins = Cpt(EpicsSignal, "WaitForPlugins", string=True, kind="config")

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.stage_sigs["wait_for_plugins"] = "Yes"

#     def ensure_nonblocking(self):
#         self.stage_sigs["wait_for_plugins"] = "Yes"
#         for c in self.parent.component_names:
#             cpt = getattr(self.parent, c)
#             if cpt is self:
#                 continue
#             if hasattr(cpt, "ensure_nonblocking"):
#                 cpt.ensure_nonblocking()


class PilatusDetectorCamV33(PilatusDetectorCam):
    """This is used to update the standard prosilica to AD33."""

    wait_for_plugins = Cpt(EpicsSignal, "WaitForPlugins", string=True, kind="config")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs["wait_for_plugins"] = "Yes"

    def ensure_nonblocking(self):
        self.stage_sigs["wait_for_plugins"] = "Yes"
        for c in self.parent.component_names:
            cpt = getattr(self.parent, c)
            if cpt is self:
                continue
            if hasattr(cpt, "ensure_nonblocking"):
                cpt.ensure_nonblocking()


class PilatusV33(SingleTriggerV33, PilatusDetector):
    cam = Cpt(PilatusDetectorCamV33, "cam1:")
    image = Cpt(ImagePlugin, "image1:")
    stats1 = Cpt(StatsPluginV33, "Stats1:")
    stats2 = Cpt(StatsPluginV33, "Stats2:")
    stats3 = Cpt(StatsPluginV33, "Stats3:")
    stats4 = Cpt(StatsPluginV33, "Stats4:")
    stats5 = Cpt(StatsPluginV33, "Stats5:")
    roi1 = Cpt(ROIPlugin, "ROI1:")
    roi2 = Cpt(ROIPlugin, "ROI2:")
    roi3 = Cpt(ROIPlugin, "ROI3:")
    roi4 = Cpt(ROIPlugin, "ROI4:")
    proc1 = Cpt(ProcessPlugin, "Proc1:")

    tiff = Cpt(
        TIFFPluginWithFileStore,
        suffix="TIFF1:",
        write_path_template="/nsls2/chx/%Y/%m/%d/",
        root="/nsls2/chx",
    )

    def setExposureTime(self, exposure_time, verbosity=3):
        yield from mv(
            self.cam.acquire_time,
            exposure_time,
            self.cam.acquire_period,
            exposure_time + 0.1,
        )
    def setExposurePeriod(self, exposure_period, verbosity=3):
        yield from mv(self.cam.acquire_period, exposure_period)

    def setExposureNumber(self, exposure_number, verbosity=3):
        yield from mv(self.cam.num_images, exposure_number)


class Pilatus800V33(SingleTriggerV33, PilatusDetector):
    cam = Cpt(PilatusDetectorCamV33, "cam1:")
    image = Cpt(ImagePlugin, "image1:")
    stats1 = Cpt(StatsPluginV33, "Stats1:")
    stats2 = Cpt(StatsPluginV33, "Stats2:")
    stats3 = Cpt(StatsPluginV33, "Stats3:")
    stats4 = Cpt(StatsPluginV33, "Stats4:")
    stats5 = Cpt(StatsPluginV33, "Stats5:")
    roi1 = Cpt(ROIPlugin, "ROI1:")
    roi2 = Cpt(ROIPlugin, "ROI2:")
    roi3 = Cpt(ROIPlugin, "ROI3:")
    roi4 = Cpt(ROIPlugin, "ROI4:")
    proc1 = Cpt(ProcessPlugin, "Proc1:")

    tiff = Cpt(
        TIFFPluginWithFileStore,
        suffix="TIFF1:",
        read_path_template="/nsls2/data/chx/legacy/data/%Y/%m/%d/",
        write_path_template="/nsls2/data/chx/legacy/data/%Y/%m/%d/",
        root="/nsls2/data/chx/legacy/data",
    )
    # root='/')

    def setExposureTime(self, exposure_time, verbosity=3):
        yield from mv(
            self.cam.acquire_time,
            exposure_time,
            self.cam.acquire_period,
            exposure_time + 0.1,
        )
        # self.cam.acquire_time.put(exposure_time)
        # self.cam.acquire_period.put(exposure_time+.1)
        # caput('XF:11BMB-ES{Det:PIL2M}:cam1:AcquireTime', exposure_time)
        # caput('XF:11BMB-ES{Det:PIL2M}:cam1:AcquirePeriod', exposure_time+0.1)

    def setExposurePeriod(self, exposure_period, verbosity=3):
        yield from mv(self.cam.acquire_period, exposure_period)

    def setExposureNumber(self, exposure_number, verbosity=3):
        yield from mv(self.cam.num_images, exposure_number)


class Pilatus800V33(PilatusV33):
    tiff = Cpt(
        TIFFPluginWithFileStore,
        suffix="TIFF1:",
        write_path_template="/nsls2/data/chx/legacy/data/%Y/%m/%d/",
        root="/nsls2/data/chx/legacy/data",
    )
Pilatus800_on = True
if Pilatus800_on == True:
    pilatus800 = Pilatus800V33("XF:11IDB-ES{Det:P800k}", name="pilatus800")
    pilatus800.tiff.read_attrs = []
    pilatus800.stats3.total.kind = "hinted"
    pilatus800.stats4.total.kind = "hinted"
    STATS_NAMES = ["stats1", "stats2", "stats3", "stats4", "stats5"]
    pilatus800.read_attrs = ["tiff"] + STATS_NAMES
    for stats_name in STATS_NAMES:
        stats_plugin = getattr(pilatus800, stats_name)
        stats_plugin.read_attrs = ["total"]

    for item in pilatus800.stats1.configuration_attrs:
        item_check = getattr(pilatus800.stats1, item)
        item_check.kind = "omitted"

    for item in pilatus800.stats2.configuration_attrs:
        item_check = getattr(pilatus800.stats2, item)
        item_check.kind = "omitted"

    for item in pilatus800.stats3.configuration_attrs:
        item_check = getattr(pilatus800.stats3, item)
        item_check.kind = "omitted"

    for item in pilatus800.stats4.configuration_attrs:
        item_check = getattr(pilatus800.stats4, item)
        item_check.kind = "omitted"

    for item in pilatus800.stats5.configuration_attrs:
        item_check = getattr(pilatus800.stats5, item)
        item_check.kind = "omitted"

    for item in pilatus800.tiff.configuration_attrs:
        item_check = getattr(pilatus800.tiff, item)
        item_check.kind = "omitted"

    for item in pilatus800.cam.configuration_attrs:
        item_check = getattr(pilatus800.cam, item)
        item_check.kind = "omitted"
else:
    pilatus800 = "Pil800ISNOTWORKING"

# pilatus800_2 section  changed by RL, 20210831
# if False:
# if True:XF:11IDB-ES{Det:P800k}cam1:AcquireTime

def get_stage_sigs(dev, dd):
    for cpt_name in dev.component_names:
        cpt = getattr(dev, cpt_name)
        if hasattr(cpt, "stage_sigs"):
            dd.update(cpt.stage_sigs)
        if hasattr(cpt, "component_names"):
            get_stage_sigs(cpt, dd)


def stage_unstage_forever_plan(det):
    i = 0
    print("Started the stage_unstage_plan, running infinite loop...")
    while True:
        i += 1
        # print(f"Staging {i}th time")
        yield from bps.stage(det)
        yield from bps.unstage(det)


def trigger_forever_plan(det):
    i = 0
    print("Started the stage_unstage_plan, running infinite loop...")
    while True:
        i += 1
        # print(f"Staging {i}th time")
        yield from bps.stage(det)
        yield from bps.trigger(det, group="det")
        yield from bps.wait("det")
        yield from bps.unstage(det)


def count_forever_plan(det):
    i = 0
    print("Started the count_forever plan, running infinite loop...")
    while True:
        i += 1
        # print(f"Staging {i}th time")
        yield from bp.count([det])


def stage_unstage_once_plan(det):
    # print(f"Staging {i}th time")
    yield from bps.stage(det)
    yield from bps.unstage(det)


def count_no_save_plan(det):
    # print(f"Staging {i}th time")
    yield from bps.stage(det)
    yield from bps.trigger(det)
    yield from bps.unstage(det)


# to get stage sigs
# from collections import OrderedDict
# stage_sigs = OrderedDict()
# get_stage_sigs(pilatus2M, stage_sigs)


#######################################################

# pilatus_name = pilatus300
# pilatus_Epicsname = '{Det:SAXS}'
