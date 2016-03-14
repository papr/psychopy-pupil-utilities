import os
from psychopy import core, visual
from psychopy.visual import ImageStim, Rect
from psychopy.visual.basevisual import BaseVisualStim, ContainerMixin

module_loc = os.path.dirname(os.path.realpath(__file__))
marker_loc_format = os.path.join(module_loc,'marker_images','marker_%02d.png')

def marker_image_path(mID):
    if mID not in range(64):
        raise ValueError("Marker id has to be in range of 0 - 63")
    return marker_loc_format%mID

def _enumerateTuplesWithValues(values,remove_median=False):
    tuples = []
    for val1 in values:
        for val2 in values:
                tuples.append((val1,val2))
    if remove_median:
        tuples.pop(len(tuples)/2)
    return tuples

class SurfaceMarkers(BaseVisualStim,ContainerMixin):
    """docstring for SurfaceMarkers"""
    def __init__(self,
                 win,
                 markerIDs=range(42,50),
                 screen_pos=_enumerateTuplesWithValues([0.0,0.5,1.0],remove_median=True),
                 size=100,
                 units="",
                 name=None,
                 autoLog=None):
        self.border = 10
        if len(markerIDs) != 8:
            raise ValueError('markerIDs has to contain 8 ids in range of 0 - 63')
        super(SurfaceMarkers, self).__init__(win,units=units, name=name, autoLog=False)
        marker_locs = [marker_image_path(mID) for mID in markerIDs]
        self.marker_stim = [ImageStim(win,image=mloc,size=size) for mloc in marker_locs]
        self.marker_bg = [Rect(win,lineWidth=0.0,fillColor='white') for mloc in marker_locs]
        self.screen_pos = screen_pos
        self._setMarkerPositions()

    @property        
    def size(self):
        return self.marker_stim[0].size + self.border*2

    @size.setter
    def size(self,value):
        for stim in self.marker_stim:
            stim.size = value
        for bg in self.marker_bg:
            bg.size = value + self.border*2

    def _setMarkerPositions(self):
        size = self.win.size
        for (i, (x,y)) in enumerate(self.screen_pos):
            img = self.marker_stim[i]
            bg = self.marker_bg[i]
            pos = list(size)
            pos[0] = pos[0] * x - size[0]/2.
            pos[1] = pos[1] * y - size[1]/2.
            
            w,h = tuple(img.size / 2.0)
            w += self.border
            h += self.border
            if pos[0] - w < -size[0]/2:
                pos[0] += -size[0]/2 - (pos[0] - w)
            if pos[0] + w > size[0]/2:
                pos[0] += size[0]/2 - (pos[0] + w)
            if pos[1] - h < -size[1]/2:
                pos[1] += -size[1]/2 - (pos[1] - h)
            if pos[1] + h > size[1]/2:
                pos[1] += size[1]/2 - (pos[1] + h)

            img.pos = tuple(pos)
            bg.width = img.size[0] + self.border*2
            bg.height = img.size[1] + self.border*2
            bg.pos = tuple(pos)


    def draw(self):
        for bg in self.marker_bg:
            bg.draw()
        for stim in self.marker_stim:
            stim.draw()

__all__ = ['SurfaceMarkers', 'marker_image_path', 'marker_loc_format']