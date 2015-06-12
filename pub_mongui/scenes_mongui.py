try:
    from pyqtgraph.Qt import QtGui, QtCore
except ImportError:
    raise ImportError('Ruh roh. You need to set up pyqtgraph before you can use this GUI.')

import pyqtgraph as pg
from custom_piechart_class import PieChartItem
# catch ctrl+C to terminate the program
import signal
# sleeps
import time
# dstream import
from dstream.ds_api import ds_reader
# pub_dbi import
from pub_dbi import pubdb_conn_info


# DB interface:
global dbi
dbi = ds_reader(pubdb_conn_info.reader_info())

#Establish a connection to the database through the DBI
try:
    dbi.connect()
except:
    print "Unable to connect to database... womp womp :("

#suppress warnings temporarily:
QtCore.qInstallMsgHandler(lambda *args: None)


#The QGraphicsScene class provides a surface for managing a large
#number of 2D graphical items (IE piecharts)
#The class serves as a container for QGraphicsItems.
#It is used together with QGraphicsView for visualizing 2D graphical items.
#Maybe make custom piechart return QGraphicsView (which is a widget)

#I think these are positions on the screen in which the window appears
scene_xmin, scene_ymin, scene_xmax, scene_ymax = 100, 100, 500, 500
#Assume 5x5 grid of projects
cell_width, cell_height = float(scene_xmax-scene_xmin)/float(5),float(scene_ymax-scene_ymin)/float(5)
cell_halfwidth, cell_halfheight = float(cell_width/2), float(cell_height/2)


app = QtGui.QApplication([])
## QGraphicsScene(x,y,width,height)
scene = QtGui.QGraphicsScene(scene_xmin,scene_ymin,scene_xmax-scene_xmin,scene_ymax-scene_ymin)
#print "scene xmin, ymin, width, height = (%f,%f,%f,%f)"%(scene_xmin,scene_ymin,scene_xmax-scene_xmin,scene_ymax-scene_ymin)
view = QtGui.QGraphicsView(scene)
view.show()

#Get a list of all projects from the DBI
projects = dbi.list_all_projects() # [project, command, server, sleepafter .... , enabled, resource]

# Dictionary of project name --> pie chart item
proj_dict = {}

# Loop over projects and add a viewbox plot for each in the window
# Each viewbox is initialized with a pichart w/ hard-coded data
# For now, start with a 5x5 grid, later place them on a diagram
nrows, ncols = 5, 5
rowcount, colcount = 0, 0

for iproj in projects:

    #Initialize all piecharts as filled-in yellow circles, with radius = half the width of the cell it lives in
    init_data = (colcount*cell_width+cell_halfwidth+scene_xmin, rowcount*cell_height+cell_halfheight+scene_ymin, cell_halfwidth, [ (1., 'y') ])
    #print "init data is: %f, %f, %f, [(1., 'y')]"%(colcount*cell_width+cell_halfwidth, rowcount*cell_height+cell_halfheight, 0.5*cell_halfwidth)
    ichart = PieChartItem(init_data)

    #Add the piecharts to the scene (piechart location is stored in piechart object)
    scene.addItem(ichart)
  
    #Store the piechart in a dictionary to modify it later, based on project name
    proj_dict[iproj._project] = ichart

    #Add a legend to the bottom right
    mytext = QtGui.QGraphicsTextItem()
    mytext.setPos(scene_xmin+0.75*(scene_xmax-scene_xmin),scene_ymin+0.75*(scene_ymax-scene_ymin))
    mytext.setPlainText('Legend:\nBlue: Status1\nGreen: Status2')
    myfont = QtGui.QFont()
    myfont.setPointSize(10)
    mytext.setFont(myfont)
    scene.addItem(mytext)
    
    colcount += 1
    if colcount == ncols: 
        colcount = 0
        rowcount += 1


def update_gui():

    #Get a list of all projects from the DBI
    #Need to repeat this because otherwise when one project gets disabled or something,
    #"projects" needs to be updated to reflect that
    projects = dbi.list_all_projects() # [project, command, server, sleepafter .... , enabled, resource]

    for iproj in projects:
        #First store the piechart x,y coordinate to re-draw it in the same place later
        ix, iy = proj_dict[iproj._project].getCenterPoint()

        #Status codes: 0 is completed (don't care about these) 1 is initiated, 2 is to be validated, >2 is error?
        #Get the number of runs with status 1 from project through the DBI
        n_status1 = len(dbi.get_runs(iproj._project,status=1))
        
        #Get the number of runs with status 2 from project through DBI
        n_status2 = len(dbi.get_runs(iproj._project,status=2))

        tot_n = n_status1+n_status2;

        #If no runs have status 1 or 2, set pie chart radius to 0 (invisible)
        if not tot_n:
            idata = (ix, iy, 0., [ (1., 'r') ])
        else:
                     
            #Compute the fraction of the total runs that are complete
            frac_1 = float(n_status1)/float(tot_n)
            frac_2 = float(n_status2)/float(tot_n)

            #Set the new data that will be used to make a new pie chart
            #If the project is disabled, make a filled-in red circle
            if iproj._enable == True:
                idata = (ix, iy, cell_halfwidth, [ (frac_1, 'b'), (frac_2, 'g') ] )
            else:
                idata = (ix, iy, cell_halfwidth, [ (1., 'r') ])

        #Make the replacement piechart
        ichart = PieChartItem(idata)

        #Remove the old item from the scene
        scene.removeItem(proj_dict[iproj._project])

        #Draw the new piechart in the place of the old one
        scene.addItem(ichart)

        #Save the new pie chart in the dictionary, overwriting the old
        proj_dict[iproj._project] = ichart

        #Re-draw the text on top of the pie chart with the project name
        mytext = QtGui.QGraphicsTextItem()
        mytext.setPos(ix-cell_halfwidth,iy-0.5*cell_halfheight)
        mytext.setPlainText(iproj._project)
        mytext.setTextWidth(cell_width)
        myfont = QtGui.QFont()
        myfont.setPointSize(10)
        mytext.setFont(myfont)
        scene.addItem(mytext)



timer = QtCore.QTimer()
timer.timeout.connect(update_gui)
timer.start(1000) #once per second, update the plots
signal.signal(signal.SIGINT, signal.SIG_DFL)

if __name__ == '__main__':
    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()
