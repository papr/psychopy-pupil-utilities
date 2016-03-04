# CBSC: callback status codes
#  > 0: Task not done
# == 0: Task finished gracefully
#  < 0: Task failed

# calibration callback events
CALIBRATION_MARKER_MOVED_TOO_QUICKLY = CAL_MMTQ = 13
CALIBRATION_STEADY_MARKER_FOUND      = CAL_SMF  = 12
CALIBRATION_SAMPLE_COMPLETED         = CAL_SC   = 11
CALIBRATION_SUCCESSFULL              = CAL_SUC  = 10
CALIBRATION_FAILED                   = CAL_FAIL = -11

# recording callback events
RECORDING_STARTED                    = REC_STA  = 21
RECORDING_STOPPED                    = REC_STO  = 20
RECORDING_SOURCE_PUPIL_INTERFACE     = REC_SRC  = 'Pupil Interface'

RECEIVED_GAZE_POSITIONS              = RCV_GAZE = 30