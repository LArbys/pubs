try:
    from pyqtgraph.Qt import QtGui, QtCore
except ImportError:
    raise ImportError('Ruh roh. You need to set up pyqtgraph before you can use this GUI.')

import pyqtgraph as pg
from custom_piechart_class import PieChartItem
from custom_qgraphicsscene import CustomQGraphicsScene
from custom_qgraphicsview  import CustomQGraphicsView
from gui_utils_api import GuiUtilsAPI

# catch ctrl+C to terminate the program
import signal
# exponential in piechart radius calculation
import math
# accessing PUBS environment variables
import os
# GUI parameter reader
from load_params import getParams
# Project description text-file parser
from load_proj_descriptions import getProjectDescriptions
# dstream import
from dstream.ds_api import ds_reader
# pub_dbi import
from pub_dbi import pubdb_conn_info

#to-do: it takes like 5 seconds to loop through projects and do all the necessary queries to build their pie charts...
#this definitely should be faster.

_update_period = 10#in seconds
my_template = 'pubs_diagram_061515.png'

# GUI DB interface:
gdbi = GuiUtilsAPI()

#suppress warnings temporarily:
QtCore.qInstallMsgHandler(lambda *args: None)

#Always start with this
app = QtGui.QApplication([])

#Load in the background image via pixmap
pm = QtGui.QPixmap(os.environ['PUB_TOP_DIR']+'/pub_mongui/gui_template/'+my_template)

#Make the scene the same size as the background template
scene_xmin, scene_ymin, scene_width, scene_height = 0, 0, pm.width(), pm.height()

#Make the scene the correct size
scene = CustomQGraphicsScene(scene_xmin,scene_ymin,scene_width,scene_height)
#Add the background pixmap to the scene
mypm = scene.addPixmap(pm)
#Set the background so it's upper-left corner matches upper-left corner of scene
mypm.setPos(scene_xmin,scene_ymin)

#Make custom (zoomable) view from the scene and show it
view = CustomQGraphicsView(scene)
#Enforce the view to align with upper-left corner
view.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
view.show()

#For now, zoom out a little bit so it can fit on my screen ...
view.scale(0.8,0.8)

#Get a list of all projects from the gui DBI
projects = gdbi.getAllProjects() # [project, command, server, sleepafter .... , enabled, resource]

# Dictionary of project name --> pie chart item
proj_dict = {}

#Read in the parameters for this template into a dictionary
#These dictate, based on project name, where to draw on GUI
template_params = getParams(my_template)

#Read in the project descriptions stored in a separate text file
proj_descripts = getProjectDescriptions()

for iproj in projects:

    iprojname = iproj._project

    if iprojname not in template_params:
        print "Uh oh. Project %s doesn't have parameters to load it to the template. I will not draw this project." % iprojname
        continue    
    
    #Initialize all piecharts as filled-in yellow circles, with radius = max radius for that project
    xloc, yloc, maxradius = template_params[iprojname]
    xloc, yloc, maxradius = float(xloc), float(yloc), float(maxradius)
    ichart = PieChartItem((iprojname,scene_xmin+scene_width*xloc, scene_ymin+scene_height*yloc, maxradius, [ (1., 'y') ]))
    #Initialize the piechart description from the stored text file
    if iprojname in proj_descripts.keys():
        ichart.setDescript(proj_descripts[iprojname])
        
    #Add the piecharts to the scene (piechart location is stored in piechart object)
    scene.addItem(ichart)
  
    #Store the piechart in a dictionary to modify it later, based on project name
    proj_dict[iprojname] = ichart

    #Add a legend to the bottom right #to do: make legend always in foreground
    mytext = QtGui.QGraphicsTextItem()
    mytext.setPos(scene_xmin+0.80*scene_width,scene_height*0.90)
    mytext.setPlainText('Legend:\nBlue: Status1\nGreen: Status2\nRed: Project Disabled')
    mytext.setDefaultTextColor(QtGui.QColor('white'))
    myfont = QtGui.QFont()
    myfont.setPointSize(10)
    mytext.setFont(myfont)
    scene.addItem(mytext)
    
def update_gui():

    #Get a list of all projects from the DBI
    #Need to repeat this because otherwise when one project gets disabled or something,
    #"projects" needs to be updated to reflect that
    projects = gdbi.getAllProjects()

    for iproj in projects:

        iprojname = iproj._project

        #If this project isn't in the dictionary (I.E. it wasn't ever drawn on the GUI),
        #then skip it. This can be fixed by adding the project to the GUI params
        if iprojname not in proj_dict.keys():
            continue

        #First store the piechart x,y coordinate
        ix, iy = proj_dict[iprojname].getCenterPoint()
        #Get the maximum radius of for this pie chart from the template parameters
        max_radius = float(template_params[iprojname][2])
        #Compute the number of entries in the pie chart (denominator)
        tot_n = gdbi.getNRunSubruns(iprojname)
        #Compute the radius if the pie chart, based on the number of entries
        ir = gdbi.computePieRadius(iprojname, max_radius, tot_n)
        #Compute the slices of the pie chart
        pie_slices = gdbi.computePieSlices(iprojname, tot_n)

        #To do:
        #Check if the pie chart has changed since last update
        #If it hasn't changed, don't bother re-drawing it
        
        #Set the new data that will be used to make a new pie chart
        #If the project is disabled, make a filled-in red circle
        if iproj._enable == True:
            idata = (iprojname, ix, iy, ir, pie_slices )
        else:
            idata = (iprojname, ix, iy, ir, [ (1., 'r') ] )

        #To-do: play around with what is being done (removing+adding)
        #to try to speed up this code

        #Remove the old item from the scene
        scene.removeItem(proj_dict[iprojname])

        #update the piechart item with the new data
        proj_dict[iprojname].updateData(idata)
        proj_dict[iprojname].appendHistory(tot_n)

        #Draw the new piechart in the place of the old one
        scene.addItem(proj_dict[iprojname])

        #On top of the pie chart, write the number of run/subruns
        #Re-draw the text on top of the pie chart with the project name
        mytext = QtGui.QGraphicsTextItem()
        mytext.setPos(ix,iy)
        mytext.setPlainText(str(tot_n)+'\nRun/Subruns')
        mytext.setDefaultTextColor(QtGui.QColor('white'))
        #mytext.setTextWidth(50)
        myfont = QtGui.QFont()
        myfont.setBold(True)
        myfont.setPointSize(10)
        mytext.setFont(myfont)
        scene.addItem(mytext)

#Initial drawing of GUI with real values
#This is also the function that is called to update the canvas periodically
update_gui()

timer = QtCore.QTimer()
timer.timeout.connect(update_gui)
timer.start(_update_period*1000.) #Frequency with which to update plots, in milliseconds

#Catch ctrl+C to close things
signal.signal(signal.SIGINT, signal.SIG_DFL)


if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()