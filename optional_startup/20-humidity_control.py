#### functions and settings related to the humidity controller ##############

pv_rh='XF:11IDB-ES{IO}AI:1Avg-I'
pv_wet_flow='XF:11IDB-ES{IO}AO:1'
pv_dry_flow='XF:11IDB-ES{IO}AO:2'
pv_T='XF:11IDB-ES{IO:RTD}T:1'

def set_ioLogik_labels_humidity_setup():
    caput('XF:11IDB-ES{IO}AO:1-SP.DESC','wet flow [0-5] V')
    caput('XF:11IDB-ES{IO}AO:2-SP.DESC','dry flow [0-5] V')
    caput('XF:11IDB-ES{IO:RTD}T:1-I.DESC','T humidity sensor')
    caput('XF:11IDB-ES{IO}AI:1-I.DESC','raw reading rh')

def reset_ioLogik_labels_humidity_setup():
    caput('XF:11IDB-ES{IO}AO:1-SP.DESC','AO Chan1 (0-10V)')
    caput('XF:11IDB-ES{IO}AO:2-SP.DESC','AO Chan2 (0-10V)')
    caput('XF:11IDB-ES{IO:RTD}T:2-I.DESC','RTD Channel 1')
    caput('XF:11IDB-ES{IO}AI:1-I.DESC','AI Chan1 (0-10V)')

def set_dry_flow(voltage=0):
    if voltage > 5:
        voltage=5;print('dry flow voltage set to maximum of 5V!')
    if voltage <0:
        voltage=0; print('dry flow voltage set to minimum of 0V!')
    caput(pv_dry_flow+'-SP',voltage);print('dry flow voltage set to %s V'%voltage)
    
def read_dry_flow(verbose=True):
    df=caget(pv_dry_flow+'-RB')
    if verbose==True:
        print('voltage on dry-flow channel: %s V'%df)
    elif verbose==False:
        return df
        
def set_wet_flow(voltage=0):
    if voltage > 5:
        voltage=5;print('wet flow voltage set to maximum of 5V!')
    if voltage <0:
        voltage=0; print('wet flow voltage set to minimum of 0V!')
    caput(pv_wet_flow+'-SP',voltage);print('wet flow voltage set to %s V'%voltage)
    
def read_wet_flow(verbose=True):
    df=caget(pv_wet_flow+'-RB')
    if verbose==True:
        print('voltage on wet-flow channel: %s V'%df)
    elif verbose==False:
        return df

def set_flows(dry=0,wet=0):
    set_dry_flow(dry);set_wet_flow(wet)
    
def read_flows(verbose=True):
    dfd=read_dry_flow(verbose=False)
    dfw=read_wet_flow(verbose=False)
    if verbose == True:
        print('dry flow: %s V   wet flow: %s V'%(dfd,dfw))
    
def read_rhT(verbose=True):
   rhT=caget(pv_T+'Avg-I')
   if verbose==True:
       print('temperature at humidity sensor: %sC'%rhT)
   elif verbose==False:
       return rhT
def setup_rh_pv(sensor='humidity_generator',voltage_supply=5):
    #sensor_dict={'humidity_generator':{'coeff_offset':0.819540,'coeff_slope':0.029042974}}
    sensor_dict={'humidity_generator':{'coeff_offset':0.819540,'coeff_slope':0.029942974}} #re-calibrated
    caput('XF:11ID-CT{}DB:1userCalc10.SCAN',2)
    caput('XF:11ID-CT{}DB:1userCalc10.INAN',pv_rh)
    caput('XF:11ID-CT{}DB:1userCalc10.INBN',pv_T+'Avg-I')
    caput('XF:11ID-CT{}DB:1userCalc10.C',sensor_dict[sensor]['coeff_offset'])
    caput('XF:11ID-CT{}DB:1userCalc10.D',sensor_dict[sensor]['coeff_slope'])
    caput('XF:11ID-CT{}DB:1userCalc10.E',voltage_supply)
    caput('XF:11ID-CT{}DB:1userCalc10.CALC','((A*5/E-C)/D)/(1.0546-0.00216*B)')
    caput('XF:11ID-CT{}DB:1userCalc10.OUTN','XF:11ID-CT{ES:1}ao1') 
    caput('XF:11ID-CT{ES:1}ao1.DESC','relative Humidity [%]')

def setup_rh_pid():
    # this sets up the dry gas input and insures value is 0-100 [%]
    caput('XF:11ID-CT{ES:1}ai1.DESC','dry GN2 [0-100%]')
    caput('XF:11ID-CT{}DB:1userCalc9.SCAN',2)
    caput('XF:11ID-CT{}DB:1userCalc9.INAN','XF:11ID-CT{ES:1}ai1')
    caput('XF:11ID-CT{}DB:1userCalc9.CALC','min(max(A,0),100)')
    caput('XF:11ID-CT{}DB:1userCalc9.OUTN','XF:11ID-CT{ES:1}ai1')
    # this calulates the output voltage corresponding to the requested dry gas flow and set the PLC output voltage
    caput('XF:11ID-CT{}DB:1userCalc8.SCAN',2)
    caput('XF:11ID-CT{}DB:1userCalc8.INAN','XF:11ID-CT{ES:1}ai1')
    caput('XF:11ID-CT{}DB:1userCalc8.CALC','A*.05')
    caput('XF:11ID-CT{}DB:1userCalc8.OUTN',pv_dry_flow+'-SP')
    # this sets up the RH setpoint and makes sure it' in the range 0-100%
    caput('XF:11ID-CT{ES:1}ai2.DESC','RH [0-100%] SETPOINT')
    caput('XF:11ID-CT{}DB:1userCalc7.SCAN',2)
    caput('XF:11ID-CT{}DB:1userCalc7.INAN','XF:11ID-CT{ES:1}ai2')
    caput('XF:11ID-CT{}DB:1userCalc7.OUTN','XF:11ID-CT{ES:1}ai2')
    caput('XF:11ID-CT{}DB:1userCalc7.CALC','min(max(A,0),100)')





def read_rh(temperature=25,sensor='humidity_generator',verbose=True,voltage_supply=5):
    if temperature == 'auto':
        temperature=read_rhT(verbose=False)
    voltage_out = caget(pv_rh)
    corr_voltage_out = voltage_out * (5.0 / voltage_supply)
    if sensor=='humidity_generator':
        coeff_offset = 0.819540
        coeff_slope = 0.029042974
    sensor_RH = (corr_voltage_out - coeff_offset) / coeff_slope
    true_RH = sensor_RH / (1.0546 - 0.00216 * temperature)      # T in [degC]
    if verbose == True:
        print('Raw sensor RH = {:.3f} pct.'.format(sensor_RH))
        print('T-corrected RH = {:.3f} pct at {:.3f} degC.'.format(true_RH, temperature))
    return true_RH
    
def rh_control(rh_target=50,control_flow='wet',tolerance=1,update_period=10,correction_step=.025):
    while 1>0:
        sleep(update_period)
        cur_rh=read_rh(temperature='auto')
        print('\ncurrent relative humidity: %s [perc.] -> target: %s [perc.]'%(np.round(cur_rh,2),rh_target))
        if np.abs(cur_rh-rh_target)>tolerance:
            if cur_rh < rh_target and control_flow=='wet':
                set_wet_flow(read_wet_flow(verbose=False)+correction_step)
            elif cur_rh < rh_target and control_flow=='dry':
                set_dry_flow(read_dry_flow(verbose=False)-correction_step)
            elif cur_rh > rh_target and control_flow=='wet':
                set_wet_flow(read_wet_flow(verbose=False)-correction_step)
            elif cur_rh < rh_target and control_flow=='dry':
                set_dry_flow(read_dry_flow(verbose=False)+correction_step)

  
  
  

    
   
    
    



#def read_Humidity(): 
    #ioL = ioLogik()       
#    return ioL.readRH(AI_chan=1, temperature=25, verbosity=3)


#set the gas flow between 1V and 5V


#def setFlow(self,channel, voltage=0):
    #device = 'A1'
#    ioL.set(AO[channel], voltage)

#def readFlow(self,channel):
    #device = 'A1'
#    ioL.read(AO[channel])    

#def setDryFlow(self,voltage=None):
#    if voltage==None or voltage>5 or voltage <0:
#        print('Input voltage betwee 0 and 5V')
#       setFlow(1, voltage=0)
#        setFlow(1, voltage=voltage)

#def setWetFlow(self,voltage=0):
#    if voltage==None or voltage>5 or voltage <0:
#        print('Input voltage betwee 0 and 5V')
#        setFlow(2, voltage=0)
#        setFlow(2, voltage=voltage)
        
#def setTwoFlows(self,dryV=None, wetV=None): 
#    selfWetFlow(wetV)
#    selfDryFlow(dryV)

