# -*- coding: ISO-8859-15 -*-
# =============================================================================
# Copyright (c) 2004, 2006 Sean C. Gillies
# Copyright (c) 2007 STFC <http://www.stfc.ac.uk>
#
# Authors : 
#          Dominic Lowe <d.lowe@rl.ac.uk>
#
# Contact email: d.lowe@rl.ac.uk
# =============================================================================

from wcsBase import WCSBase, WCSCapabilitiesReader, RereadableURL
from urllib import urlencode
from urllib2 import urlopen
from owslib.etree import etree
import os, errno

#  function to save writing out WCS namespace in full each time
def ns(tag):
    return '{http://www.opengis.net/wcs}'+tag

class ServiceException(Exception):
    pass


class WebCoverageService_1_0_0(WCSBase):
    """Abstraction for OGC Web Coverage Service (WCS), version 1.0.0
    Implements IWebCoverageService.
    """
    def __getitem__(self,name):
        ''' check contents dictionary to allow dict like access to service layers'''
        if name in self.__getattribute__('contents').keys():
            return self.__getattribute__('contents')[name]
        else:
            raise KeyError, "No content named %s" % name
    
    def __init__(self,url,xml):
        self.version='1.0.0'
        self.url = url   
        # initialize from saved capability document or access the server
        reader = WCSCapabilitiesReader(self.version)
        if xml:
            self._capabilities = reader.readString(xml)
        else:
            self._capabilities = reader.read(self.url)

        #serviceIdentification metadata
        subelem=self._capabilities.find(ns('Service/'))
        self.identification=ServiceIdenfication(subelem)                               
                   
        #serviceProvider metadata
        self.provider=None
        subelem=self._capabilities.find(ns('Service/')+ns('responsibleParty'))
        if subelem is not None:
            self.provider=ServiceProvider(subelem)   
        
        #serviceOperations metadata
        self.operations=[]
        for elem in self._capabilities.find(ns('Capability/')+ns('Request')).getchildren():
            self.operations.append(OperationMetadata(elem))
          
        #serviceContents metadata
        self.contents={}
        for elem in self._capabilities.findall(ns('ContentMetadata/')+ns('CoverageOfferingBrief')): 
            cm=ContentMetadata(elem, self)
            self.contents[cm.id]=cm
        
        #exceptions
        self.exceptions = [f.text for f \
                in self._capabilities.findall('Capability/Exception/Format')]
    
    
    def items(self):
        '''supports dict-like items() access'''
        items=[]
        for item in self.contents:
            items.append((item,self.contents[item]))
        return items
    
      
  
    def getCoverage(self, identifier=None, bbox=None, time=None, format = None,  crs=None, width=None, height=None, resx=None, resy=None, resz=None,parameter=None,method='Get',**kwargs):
        """Request and return a coverage from the WCS as a file-like object
        note: additional **kwargs helps with multi-version implementation
        core keyword arguments should be supported cross version
        example:
        cvg=wcs.getCoverage(identifier=['TuMYrRQ4'], timeSequence=['2792-06-01T00:00:00.0'], bbox=(-112,36,-106,41),format='cf-netcdf')

        is equivalent to:
        http://myhost/mywcs?SERVICE=WCS&REQUEST=GetCoverage&IDENTIFIER=TuMYrRQ4&VERSION=1.1.0&BOUNDINGBOX=-180,-90,180,90&TIMESEQUENCE=['2792-06-01T00:00:00.0']&FORMAT=cf-netcdf
           
        """
        
        self.log.debug('WCS 1.0.0 DEBUG: Parameters passed to GetCoverage: identifier=%s, bbox=%s, time=%s, format=%s, crs=%s, width=%s, height=%s, resx=%s, resy=%s, resz=%s, parameter=%s, method=%s, other_arguments=%s'%(identifier, bbox, time, format, crs, width, height, resx, resy, resz, parameter, method, str(kwargs)))
                
        base_url = self.getOperationByName('GetCoverage').methods[method]['url']
        
        self.log.debug('WCS 1.0.0 DEBUG: base url of server: %s'%base_url)
        
        #process kwargs
        request = {'version': self.version, 'request': 'GetCoverage', 'service':'WCS'}
        assert len(identifier) > 0
        request['Coverage']=identifier
        #request['identifier'] = ','.join(identifier)
        if bbox:
            request['BBox']=','.join([str(x) for x in bbox])
        else:
            request['BBox']=None
        if time:
            request['time']=','.join(time)
        if crs:
            request['crs']=crs
        request['format']=format
        if width:
            request['width']=width
        if height:
            request['height']=height
        if resx:
            request['resx']=resx
        if resy:
            request['resy']=resy
        if resz:
            request['resz']=resz
        
        #anything else e.g. vendor specific parameters must go through kwargs
        if kwargs:
            for kw in kwargs:
                request[kw]=kwargs[kw]
        
        #encode and request
        data = urlencode(request)
        self.log.debug('WCS 1.0.0 DEBUG: Second part of URL: %s'%data)
        try:
            u = urlopen(base_url+data)
            self.log.debug('WCS 1.0.0 DEBUG: called urlopen(base_url+data)')
        except:  
            u = urlopen(base_url, data=data)    
            self.log.debug('WCS 1.0.0 DEBUG: called urlopen(base_url, data=data)')
        
        self.log.debug('WCS 1.0.0 DEBUG: GetCoverage request made: %s'%u.url)
        self.log.debug('WCS 1.0.0 DEBUG: Headers returned: %s'%str(u.headers))
        # check for service exceptions, and return #TODO - test this bit properly.
        if u.info()['Content-Type'] == 'text/xml':          
            #going to have to read the xml to see if it's an exception report.
            #wrap the url stram in a extended StringIO object so it's re-readable
            u=RereadableURL(u)      
            se_xml= u.read()
            se_tree = etree.fromstring(se_xml)
            serviceException=se_tree.find('{http://www.opengis.net/ows}Exception')
            if serviceException is not None:
                raise ServiceException, \
                str(serviceException.text).strip()
            u.seek(0)
        return u
               
    def getOperationByName(self, name):
        """Return a named operation item."""
        for item in self.operations:
            if item.name == name:
                return item
        raise KeyError, "No operation named %s" % name
    
class OperationMetadata(object):
    """Abstraction for WCS metadata.   
    Implements IMetadata.
    """
    def __init__(self, elem):
        """."""
        self.name = elem.tag.split('}')[1]          
        
        #self.formatOptions = [f.text for f in elem.findall('{http://www.opengis.net/wcs/1.1/ows}Parameter/{http://www.opengis.net/wcs/1.1/ows}AllowedValues/{http://www.opengis.net/wcs/1.1/ows}Value')]
        methods = []
        for resource in elem.findall(ns('DCPType/')+ns('HTTP/')+ns('Get/')+ns('OnlineResource')):
            url = resource.attrib['{http://www.w3.org/1999/xlink}href']
            methods.append(('Get', {'url': url}))        
        for resource in elem.findall(ns('DCPType/')+ns('HTTP/')+ns('Post/')+ns('OnlineResource')):
            url = resource.attrib['{http://www.w3.org/1999/xlink}href']
            methods.append(('Post', {'url': url}))        
        self.methods = dict(methods)
            
class ServiceIdenfication(object):
    """ Abstraction for ServiceIdentification metadata """
    def __init__(self,elem):
        # properties              
        self.version='1.0.0'
        self.service = elem.find(ns('name')).text
        try:
            self.abstract = elem.find(ns('description')).text
        except:
            self.abstract=None
        self.title = elem.find(ns('name')).text     
        self.keywords = [f.text for f in elem.findall(ns('keywords')+'/'+ns('keyword'))]
        #note: differs from 'rights' in interface
        self.fees=elem.find(ns('fees')).text
        self.accessConstraints=elem.find(ns('accessConstraints')).text
       
class ServiceProvider(object):
    """ Abstraction for WCS ResponsibleParty 
    Implements IServiceProvider"""
    def __init__(self,elem):
        name=elem.find(ns('organisationName'))
        if name is not None:
            self.name=name.text
        else:
            self.name=None
        self.url=self.name #there is no definitive place for url  WCS, repeat organisationName
        self.contact=ContactMetadata(elem)

class ContactMetadata(object):
    ''' implements IContactMetadata'''
    def __init__(self, elem):
        try:
            self.name = elem.find(ns('individualName')).text
        except AttributeError:
            self.name = None
        try:
            self.organization=elem.find(ns('organisationName')).text 
        except AttributeError:
            self.organization = None
        try:
            self.address = elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('deliveryPoint')).text
        except AttributeError:
            self.address = None
        try:
            self.city= elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('city')).text
        except AttributeError:
            self.city = None
        try:
            self.region=elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('administrativeArea')).text
        except AttributeError:
            self.region = None
        try:
            self.postcode=elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('postalCode')).text
        except AttributeError:
            self.postcode=None
        try:
            self.country=elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('country')).text
        except AttributeError:
            self.country = None
        try:
            self.email=elem.find(ns('contactInfo')+'/'+ns('address')+'/'+ns('electronicMailAddress')).text
        except AttributeError:
            self.email = None

class ContentMetadata(object):
    """
    Implements IContentMetadata
    """
    def __init__(self, elem, service):
        """Initialize. service is required so that describeCoverage requests may be made"""
        #TODO - examine the parent for bounding box info.
        
        #self._parent=parent
        self._elem=elem
        self._service=service
        self.id=elem.find(ns('name')).text
        self.title =elem.find(ns('label')).text       
        self.keywords = [f.text for f in elem.findall(ns('keywords')+'/'+ns('keyword'))]        
        self.boundingBoxWGS84 = None
        b = elem.find(ns('lonLatEnvelope')) 
        if b is not None:
            gmlpositions=b.findall('{http://www.opengis.net/gml}pos')
            lc=gmlpositions[0].text
            uc=gmlpositions[1].text
            self.boundingBoxWGS84 = (
                    float(lc.split()[0]),float(lc.split()[1]),
                    float(uc.split()[0]), float(uc.split()[1]),
                    )
        
    #grid is either a gml:Grid or a gml:RectifiedGrid if supplied as part of the DescribeCoverage response.
    def _getGrid(self):
        if not hasattr(self, 'descCov'):
                self.descCov=self._service.getDescribeCoverage(self.id)
        gridelem= self.descCov.find(ns('CoverageOffering/')+ns('domainSet/')+ns('spatialDomain/')+'{http://www.opengis.net/gml}RectifiedGrid')
        if gridelem is not None:
            grid=RectifiedGrid(gridelem)
        else:
            gridelem=self.descCov.find(ns('CoverageOffering/')+ns('domainSet/')+ns('spatialDomain/')+'{http://www.opengis.net/gml}Grid')
            grid=Grid(gridelem)
        return grid
    grid=property(_getGrid, None)
        
     #timelimits are the start/end times, timepositions are all timepoints. WCS servers can declare one or both or neither of these.
    def _getTimeLimits(self):
        timepoints, timelimits=[],[]
        b=self._elem.find(ns('lonLatEnvelope'))
        if b is not None:
            timepoints=b.findall('{http://www.opengis.net/gml}timePosition')
        else:
            #have to make a describeCoverage request...
            if not hasattr(self, 'descCov'):
                self.descCov=self._service.getDescribeCoverage(self.id)
            for pos in self.descCov.findall(ns('CoverageOffering/')+ns('domainSet/')+ns('temporalDomain/')+'{http://www.opengis.net/gml}timePosition'):
                timepoints.append(pos)
        if timepoints:
                timelimits=[timepoints[0].text,timepoints[1].text]
        return timelimits
    timelimits=property(_getTimeLimits, None)   
    
    def _getTimePositions(self):
        timepositions=[]
        if not hasattr(self, 'descCov'):
            self.descCov=self._service.getDescribeCoverage(self.id)
        for pos in self.descCov.findall(ns('CoverageOffering/')+ns('domainSet/')+ns('temporalDomain/')+'{http://www.opengis.net/gml}timePosition'):
                timepositions.append(pos.text)
        return timepositions
    timepositions=property(_getTimePositions, None)
           
            
    def _getOtherBoundingBoxes(self):
        ''' incomplete, should return other bounding boxes not in WGS84
            #TODO: find any other bounding boxes. Need to check for CoverageOffering/domainSet/spatialDomain/gml:Envelope & gml:EnvelopeWithTimePeriod.'''
        bboxes=[]
        if not hasattr(self, 'descCov'):
            self.descCov=self._service.getDescribeCoverage(self.id)
        return bboxes        
    boundingboxes=property(_getOtherBoundingBoxes,None)

    
    def _getSupportedCRSProperty(self):
        # gets supported crs info
        crss=[]
        for elem in self._service.getDescribeCoverage(self.id).findall(ns('CoverageOffering/')+ns('supportedCRSs/')+ns('responseCRSs')):
            for crs in elem.text.split(' '):
                crss.append(crs)
        for elem in self._service.getDescribeCoverage(self.id).findall(ns('CoverageOffering/')+ns('supportedCRSs/')+ns('requestResponseCRSs')):
            for crs in elem.text.split(' '):
                crss.append(crs)
        for elem in self._service.getDescribeCoverage(self.id).findall(ns('CoverageOffering/')+ns('supportedCRSs/')+ns('nativeCRSs')):
            for crs in elem.text.split(' '):
                crss.append(crs)
        return crss
    supportedCRS=property(_getSupportedCRSProperty, None)
       
       
    def _getSupportedFormatsProperty(self):
        # gets supported formats info
        frmts =[]
        for elem in self._service.getDescribeCoverage(self.id).findall(ns('CoverageOffering/')+ns('supportedFormats/')+ns('formats')):
            frmts.append(elem.text)
        return frmts
    supportedFormats=property(_getSupportedFormatsProperty, None)
        
          
#Adding classes to represent gml:grid and gml:rectifiedgrid. One of these is used for the cvg.grid property
#(where cvg is a member of the contents dictionary)     
#There is no simple way to convert the offset values in a rectifiedgrid grid to real values without CRS understanding, therefore this is beyond the current scope of owslib, so the representation here is purely to provide access to the information in the GML.
   
class Grid(object):
    ''' Simple grid class to provide axis and value information for a gml grid '''
    def __init__(self, grid):
        self.axislabels = []
        self.dimension=None
        self.lowlimits=[]
        self.highlimits=[]
        if grid is not None:
            self.dimension=int(grid.get('dimension'))
            self.lowlimits= grid.find('{http://www.opengis.net/gml}limits/{http://www.opengis.net/gml}GridEnvelope/{http://www.opengis.net/gml}low').text.split(' ')
            self.highlimits = grid.find('{http://www.opengis.net/gml}limits/{http://www.opengis.net/gml}GridEnvelope/{http://www.opengis.net/gml}high').text.split(' ')
            for axis in grid.findall('{http://www.opengis.net/gml}axisName'):
                self.axislabels.append(axis.text)
      

class RectifiedGrid(Grid):
    ''' RectifiedGrid class, extends Grid with additional offset vector information '''
    def __init__(self, rectifiedgrid):
        super(RectifiedGrid,self).__init__(rectifiedgrid)
        self.origin=rectifiedgrid.find('{http://www.opengis.net/gml}origin/{http://www.opengis.net/gml}pos').text.split()
        self.offsetvectors=[]
        for offset in rectifiedgrid.findall('{http://www.opengis.net/gml}offsetVector'):
            self.offsetvectors.append(offset.text.split())
        