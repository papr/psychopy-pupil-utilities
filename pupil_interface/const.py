# CBSC: callback status codes
#  > 0: Task not done
# == 0: Task finished gracefully
#  < 0: Task failed

# calibration callback events
EVENT_CALIBRATION_MARKER_MOVED_TOO_QUICKLY = CAL_MMTQ = 13
EVENT_CALIBRATION_STEADY_MARKER_FOUND      = CAL_SMF  = 12
EVENT_CALIBRATION_SAMPLE_COMPLETED         = CAL_SC   = 11
EVENT_CALIBRATION_SUCCESSFULL              = CAL_SUC  = 10
EVENT_CALIBRATION_FAILED                   = CAL_FAIL = -11

# recording callback events
EVENT_RECORDING_STARTED                    = REC_STA  = 21
EVENT_RECORDING_STOPPED                    = REC_STO  = 20
RECORDING_SOURCE_PUPIL_INTERFACE           = REC_SRC  = 'Pupil Interface'

EVENT_RECEIVED_GAZE_POSITIONS              = RCV_GAZE = 30

EVENT_NET_NODE_JOINED_GROUP                = NET_JOIN = 41
EVENT_NET_NODE_EXITED_GROUP                = NET_EXIT = 42

EVENT_NET_CONNECTED                        = NET_CONN = 51
EVENT_NET_DISCONNECTED                     = NET_DISC = 52

EVENT_TIMEOUT                              = TIME_OUT = -01

EVT_MAP = {}
for name in dir():
    if name.startswith('EVENT_'):
        value = locals()[name]
        EVT_MAP[value] = name