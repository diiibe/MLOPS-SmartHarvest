class MockEE(object):
    """
    Mock Earth Engine Module.
    Acts as 'ee' module when injected into sys.modules.
    """

    def __getattr__(self, name):
        # Return specific mock classes if available, else MockEEObject
        if name == "Image":
            return Image
        if name == "ImageCollection":
            return ImageCollection
        if name == "Geometry":
            return Geometry
        if name == "Filter":
            return Filter
        if name == "Date":
            return Date
        if name == "Number":
            return Number
        if name == "Reducer":
            return Reducer
        if name == "Terrain":
            return Terrain
        if name == "Algorithms":
            return Algorithms
        return MockEEObject

    def Initialize(self, *args, **kwargs):
        pass


class Algorithms(object):
    @staticmethod
    def If(condition, trueCase, falseCase):
        return trueCase


class MockEEObject:
    """Base class for all mock EE objects."""

    def __init__(self, value=None, *args, **kwargs):
        self._value = value

    def getInfo(self):
        """Mock getInfo returning dummy data or stored value."""
        if self._value is not None:
            return self._value
        return {"type": "MockObject", "data": "dummy"}

    def map(self, func):
        """Mock map: just returns self (no-op)."""
        return self

    def filter(self, *args):
        """Mock filter: returns self."""
        return self

    def filterDate(self, start, end):
        return self

    def filterBounds(self, geometry):
        return self

    def select(self, *args):
        return self

    def first(self):
        return Image()

    def projection(self):
        return "EPSG:4326"

    def mean(self):
        return Image()

    def median(self):
        return Image()

    def min(self):
        return Image()

    def max(self, *args):  # Added *args to handle max(0)
        return Image()

    def reduce(self, reducer):
        return Image()

    def rename(self, name):
        return self

    def addBands(self, *args):
        return self

    def toDouble(self):
        return self

    def toInt(self):
        return self

    def float(self):
        return self

    def multiply(self, val):
        return self

    def divide(self, val):
        return self

    def add(self, val):
        return self

    def subtract(self, val):
        return self

    def hypot(self, val):
        return self

    def date(self):
        return Date()

    def set(self, key, val):
        return self

    def copyProperties(self, source, props=None):
        return self

    def updateMask(self, mask):
        return self

    def bitwiseAnd(self, val):
        return self

    def eq(self, val):
        return self

    def And(self, other):
        return self

    def lt(self, val):
        return self

    def gt(self, val):
        return self

    def lte(self, val):
        return self

    def gte(self, val):
        return self

    def Or(self, val):
        return self

    def expression(self, expression, map):
        return self

    def resample(self, mode):
        return self

    def reproject(self, crs, scale=None):
        return self

    def size(self):
        return Number(10)

    def clip(self, geom):
        return self

    def buffer(self, dist):
        return self

    def flatten(self):
        return self

    def getDownloadURL(self, *args, **kwargs):
        return "http://dummy-url.com/data.csv"

    def area(self, *args, **kwargs):
        """Mock area calculation."""
        # Return a Number mock (or similar) that acts like a number
        # Initializing reasonable dummy area (e.g. 10000 m2)
        return Number(10000)

    def focal_mean(self, *args, **kwargs):
        return self

    def glcmTexture(self, size=None):
        return self

    def qualityMosaic(self, band):
        return self

    # Static methods usually found on ee.Image/Collection but simplified here
    @staticmethod
    def cat(images):
        return Image()

    @staticmethod
    def constant(val):
        return Image()


class Image(MockEEObject):
    pass


class ImageCollection(MockEEObject):
    def merge(self, other):
        return self

    def combine(self, other):
        return self


class Geometry(MockEEObject):
    class Polygon(MockEEObject):
        pass


class Filter(MockEEObject):
    @staticmethod
    def lt(name, val):
        return Filter()

    @staticmethod
    def calendarRange(start, end, field):
        return Filter()

    @staticmethod
    def listContains(name, val):
        return Filter()

    @staticmethod
    def eq(name, val):
        return Filter()

    @staticmethod
    def rangeContains(name, start, end):
        return Filter()


class Date(MockEEObject):
    def millis(self):
        return Number(1672531200000)  # Dummy timestamp

    def get(self, component):
        return Number(12)  # Dummy hour

    def difference(self, other, unit):
        return Number(5)


class Number(MockEEObject):
    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)


class Reducer(MockEEObject):
    @staticmethod
    def linearFit():
        return Reducer()

    @staticmethod
    def stdDev():
        return Reducer()


class Terrain(MockEEObject):
    @staticmethod
    def slope(image):
        return Image()

    @staticmethod
    def hillshade(image, azimuth, elevation):
        return Image()


# Structure to export
def Initialize(credentials=None):
    print("Mock EE Initialized")
