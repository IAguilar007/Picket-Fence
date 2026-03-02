import matplotlib.pyplot as plt
import cartopy
import cartopy.feature as cfeature
import cartopy.geodesic as geodesic
import cartopy.crs as ccrs
import cartopy.geodesic
import numpy as np
import shapely.geometry as sgeom
import warnings
import matplotlib

# Set the backend for matplotlib.
matplotlib.use("TKAgg")

class picketMap():

    def  __init__(self,picket_dict,central_station=None):
        self.pickets=picket_dict
        self.__define_extent()
        self.__unpack_central_station_params(central_station)

        self.__init_plot_params()   
        self.active_pickets=[] #TODO: Make this useful by adding a live plot
        
    def __unpack_central_station_params(self,central_station):
    
        self.central_station=central_station
        
        if central_station is not None:         
            self.central_name=list(self.central_station.keys())[0]
            self.central_lon=self.central_station[self.central_name]["Longitude"]
            self.central_lat=self.central_station[self.central_name]["Latitude"]

            if not (self.west < self.central_lon < self.east and self.south < self.central_lat < self.north):
                warnings.warn("Central station is not inside the picket radius")
        else:
            self.central_lon=(self.west + self.east)/2
            self.central_lat=(self.north + self.south)/2
        
        distances=[geodesic.Geodesic().inverse([self.central_lon,self.central_lat],[self.pickets[name]["Longitude"],self.pickets[name]["Latitude"]]) 
                   for name in self.pickets]
        self.max_distance=np.max(distances)
    
    def __define_extent(self):
    
        #Define the location of the pickets
        self.north=np.max([self.pickets[picket]["Latitude"] for picket in self.pickets])+1
        self.south=np.min([self.pickets[picket]["Latitude"] for picket in self.pickets])-1
        
        self.east=np.max([self.pickets[picket]["Longitude"] for picket in self.pickets])+1
        self.west=np.min([self.pickets[picket]["Longitude"] for picket in self.pickets])-1
    
        self.extent=[self.west, self.east, self.north, self.south]
        
        
    def __init_plot_params(self):
    
        #Add concentric circles to help understand the plot
        self.circles = []
        self.circle_text_info=[] #Longitude and latitude of the text for the circles
        
        dist_step=200 #Size of the concentric circle gaps in kilometers
        circle_num=np.arange(1,np.ceil(self.max_distance/1000/dist_step)+1,1)
        for dist in circle_num*dist_step:
            
            cp=cartopy.geodesic.Geodesic().circle(lon=self.central_lon, lat=self.central_lat, radius=1000*dist, n_samples=50, endpoint=True)
            self.circles.append(sgeom.LinearRing(cp))
            
            coord=cartopy.geodesic.Geodesic().direct([self.central_lon,self.central_lat], 180, dist*1000)
            self.circle_text_info.append([coord[0,0]-.5, #Longitude
                                          coord[0,1]+.1,#Latitude
                                          dist]) #Distance
                                            #TODO standardize this equation for text location
        

        #Add the picket fence lines
        teleseismic_R=3000 # [km] Distance to events that are considered 'teleseismic'
        self.picket_lines=[]
        for station in self.pickets:
            
            #Grab the azimuths from the observatory to the picket station
            azim_to_station=cartopy.geodesic.Geodesic().inverse([self.central_lon, self.central_lat],[self.pickets[station]["Longitude"],self.pickets[station]["Latitude"]])[0][1]
            
            #Plot on azimuths around each picket orientation
            relevant_azims=np.arange(azim_to_station-60,azim_to_station+60,1)
            
            #Find the teleseismic epicenters and their distances to the picket in question
            relevant_epicenters=cartopy.geodesic.Geodesic().direct([self.central_lon, self.central_lat],relevant_azims, 1000*teleseismic_R)[:,:2]
            dist_to_picket=cartopy.geodesic.Geodesic().inverse([self.pickets[station]["Longitude"],self.pickets[station]["Latitude"]],relevant_epicenters)[:,0]
            
            #The virtual location of the station are the coordinates with the remaining distance for surface waves to travel to the observatory
            virtual_coord_picket=cartopy.geodesic.Geodesic().direct([self.central_lon, self.central_lat],relevant_azims, 1000*teleseismic_R-dist_to_picket)[:,:2]
            
            self.picket_lines.append(sgeom.LineString(virtual_coord_picket))

        return
        
    def generate_plot(self,active_pickets=None):
        fig = plt.figure(figsize=(8, 8))
        print("Generating a new Picket Map")
        #Equidistant Azimuthal projection, preserves distances to the center point, the center should be located at the observatories.
        ax = fig.add_subplot(1, 1, 1,
                             projection=ccrs.AzimuthalEquidistant(central_longitude=self.central_lon,
                                                                  central_latitude=self.central_lat))
                              
        # Define the map features to be plotted
        ax.set_extent(self.extent)
        ax.set_facecolor("#9DB6DD") #Effectively draws the ocean a pleasing shade of blue by setting the background for the plot.
        ax.coastlines()
        #ax.add_feature(cfeature.OCEAN.with_scale('50m'))
        ax.add_feature(cfeature.LAND.with_scale('50m'),facecolor='white')
        ax.add_feature(cfeature.BORDERS.with_scale('50m'))
        ax.add_feature(cfeature.STATES)
        
        #Add circles to reference distances on the map
        ax.add_geometries(self.circles, crs=ccrs.PlateCarree(), edgecolor='gray',facecolor="none", linestyle='--') 
        for lon, lat, dist in self.circle_text_info:
            if self.south<lat<self.north:
                ax.text(lon,lat,str(int(dist))+' km',fontsize=8,transform=ccrs.Geodetic(),color='gray')
        
        #Fudge factors to improve the readability of the picket station names.  
        offset_lon=-1.6/2 #TODO: Maybe scale these with the extent of the plot
        offset_lat=-1.2/2
        
        #Add the central station and the pickets   
        if self.central_station is not None:
            ax.scatter(self.central_lon,self.central_lat, s=150,marker='*', color='black',edgecolors='black', alpha=0.7, transform=ccrs.Geodetic())
            ax.text(self.central_lon+offset_lon,self.central_lat+offset_lat,self.central_name,fontsize=10,weight='bold',transform=ccrs.Geodetic())   
        
        for station in self.pickets:
            ax.scatter(self.pickets[station]["Longitude"],self.pickets[station]["Latitude"], s=200,marker='.', color='yellow',edgecolors='black', alpha=1, transform=ccrs.Geodetic(),zorder=np.inf) #np.inf makes the picket dots always be on top
            ax.text(self.pickets[station]["Longitude"]+offset_lon,self.pickets[station]["Latitude"]+offset_lat,
                    station,fontsize=10,weight='bold',transform=ccrs.Geodetic())            
        
        #Add the picket lines             
        ax.add_geometries(self.picket_lines, crs=ccrs.PlateCarree(), edgecolor='k',facecolor="none", linestyle='-')
        
        fig.tight_layout()
        plt.show()
