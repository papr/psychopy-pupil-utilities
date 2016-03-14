from psychopy import core, visual, event
from .calibration import *
from square_markers import ScreenMarkers

win = visual.Window([1920,1000],fullscr=True,allowGUI=True, screen=0, units='pix')

c = PupilCalibrationMarker(win,radius=50,pos=(0.,0.))
s = PupilStopMarker(win,radius=50,pos=(0.,0.))
m = ScreenMarkers(win,size=100)

intro_text = visual.TextStim(win, text='Hit any key to start calibration')
intro_text.draw()
m.draw()
win.flip()
event.waitKeys()

# self-responsible drawing
offset = c.radius + m.size[0]
cal_pos = randomizedNinePointCalibrationPositions()
for pos in cal_pos:
    m.draw()
    c.drawAtCalibrationPosition(pos,offset)
    win.flip()
    event.waitKeys()

# stop calibration
m.draw()
s.drawAtCalibrationPosition((.5,.5))
win.flip()
event.waitKeys()

win.close()

core.quit()