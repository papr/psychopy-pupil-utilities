from psychopy import core, visual, event
from psychopy.visual.circle import Circle
from random import shuffle

class PupilStopMarker(Circle):
    """docstring for PupilStopMarker"""
    def __init__(self, win, **kwargs):
        """
        PupilStopMarker
        """
        #what local vars are defined (these are the init params) for use by __repr__
        self._initParams = dir()
        self._initParams.remove('self')
        #kwargs isn't a parameter, but a list of params
        self._initParams.remove('kwargs')
        self._initParams.extend(kwargs)
        kwargs['lineWidth'] = 0.
        kwargs['fillColor'] = 1.
        kwargs['edges'] = 120
        super(PupilStopMarker, self).__init__(win, **kwargs)
        self.subCircles = self._genSubCircles(win,**kwargs)

    def draw(self):
        for circ in self.subCircles:
            circ.draw()

    def __setattr__(self, name, value):
        propagate = ['pos','size','ori','opacity','interpolate','autoDraw']
        if name in propagate and hasattr(self,'subCircles'):
            for circ in self.subCircles:
                circ.__setattr__(name,value)
        else:
            super(PupilStopMarker,self).__setattr__(name,value)

    def _genSubCircles(self,win,**kwargs):
        circles = []
        for (i,s) in enumerate([6.5, 5, 4, 3, 2]):
            # generate circle with alternating black/white
            circ = self._subCircleForScale(win,s, i % 2 != 0, **kwargs)
            circles.append(circ)
        return circles
    def _subCircleForScale(self,win,scale,black,**kwargs):
        rad = scale * (self.radius/6.5)
        col = 'black' if black else 'white'
        
        kwargs['radius'] = rad
        kwargs['fillColor'] = col
        kwargs['lineWidth'] = 0.

        c = Circle(win, **kwargs)
        return c

    def drawAtCalibrationPosition(self,(x,y)):
        size = self.win.size
        pos = list(size)
        
        # calc inital position
        pos[0] = pos[0] * x - size[0]/2.
        pos[1] = pos[1] * y - size[1]/2.
        
        r = self.radius
        if pos[0] - r < -size[0]/2:
            pos[0] += -size[0]/2 - (pos[0] - r)
        if pos[0] + r > size[0]/2:
            pos[0] += size[0]/2 - (pos[0] + r)
        if pos[1] - r < -size[1]/2:
            pos[1] += -size[1]/2 - (pos[1] - r)
        if pos[1] + r > size[1]/2:
            pos[1] += size[1]/2 - (pos[1] + r)

        self.pos = tuple(pos)
        self.draw()

def ninePointCalibrationPositions():
    return [(0.,0.),(.5,0.),(1.,0.),(0.,.5),(.5,.5),(1.,.5),(0.,1.),(.5,1.),(1.,1.)]

def randomizedNinePointCalibrationPositions():
    pos = ninePointCalibrationPositions()
    shuffle(pos)
    return pos


class PupilCalibrationMarker(PupilStopMarker):
    def _genSubCircles(self,win,**kwargs):
        circles = super(PupilCalibrationMarker,self)._genSubCircles(win,**kwargs)
        circles.append(self._subCircleForScale(win,.75, True, **kwargs))
        return circles


if __name__ == '__main__':
    win = visual.Window([2560,1440],fullscr=True,allowGUI=True, screen=0, units='pix')

    c = PupilCalibrationMarker(win,radius=50,pos=(0.,0.))
    s = PupilStopMarker(win,radius=50,pos=(0.,0.))

    intro_text = visual.TextStim(win, text='Hit any key to start calibration')
    intro_text.draw()
    win.flip()
    event.waitKeys()

    # self-responsible drawing
    cal_pos = randomizedNinePointCalibrationPositions()
    for pos in cal_pos:
        c.drawAtCalibrationPosition(pos)
        win.flip()
        event.waitKeys()

    # stop calibration
    s.drawAtCalibrationPosition((.5,.5))
    win.flip()
    event.waitKeys()

    win.close()

    core.quit()