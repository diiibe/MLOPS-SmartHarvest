"""
Enhanced Mock for Google Earth Engine API.

This module provides a comprehensive mock implementation of the Earth Engine API
for offline testing. It simulates the behavior of ee objects without requiring
actual GEE authentication or network access.
"""


class MockEE:
    """
    Mock Earth Engine Module.
    Acts as 'ee' module when injected into sys.modules.
    """

    def __getattr__(self, name):
        """Return specific mock classes or MockEEObject for unknown attributes."""
        mock_classes = {
            "Image": Image,
            "ImageCollection": ImageCollection,
            "Geometry": Geometry,
            "Filter": Filter,
            "Date": Date,
            "Number": Number,
            "Reducer": Reducer,
            "Terrain": Terrain,
            "Algorithms": Algorithms,
            "FeatureCollection": FeatureCollection,
            "Feature": Feature,
        }
        return mock_classes.get(name, MockEEObject)

    def Initialize(self, *args, **kwargs):
        """Mock initialization - no-op."""
        pass


class Algorithms:
    """Mock for ee.Algorithms."""

    @staticmethod
    def If(condition, trueCase, falseCase):
        """Mock conditional - always returns true case."""
        return trueCase


class MockEEObject:
    """
    Base class for all mock EE objects.
    Provides common methods used across Image, ImageCollection, etc.
    """

    def __init__(self, value=None, *args, **kwargs):
        self._value = value
        self._properties = {}

    def getInfo(self):
        """Mock getInfo returning dummy data or stored value."""
        if self._value is not None:
            return self._value
        return {"type": "MockObject", "data": "dummy"}

    def map(self, func):
        """Mock map: applies function and returns self."""
        # In a real implementation, we'd apply func to each element
        # For testing, just return self
        return self

    def filter(self, *args):
        """Mock filter: returns self."""
        return self

    def filterDate(self, start, end):
        """Mock date filter: returns self."""
        return self

    def filterBounds(self, geometry):
        """Mock bounds filter: returns self."""
        return self

    def select(self, *args):
        """Mock band selection: returns self."""
        return self

    def first(self):
        """Mock first: returns an Image."""
        return Image()

    def projection(self):
        """Mock projection: returns EPSG:4326."""
        return Projection("EPSG:4326")

    def mean(self):
        """Mock mean reducer: returns Image."""
        return Image()

    def median(self):
        """Mock median reducer: returns Image."""
        return Image()

    def min(self):
        """Mock min reducer: returns Image."""
        return Image()

    def max(self, *args):
        """Mock max reducer: returns Image."""
        return Image()

    def reduce(self, reducer):
        """Mock reduce: returns Image."""
        return Image()

    def rename(self, name):
        """Mock rename: returns self."""
        return self

    def addBands(self, *args):
        """Mock addBands: returns self."""
        return self

    def toDouble(self):
        """Mock type conversion: returns self."""
        return self

    def toInt(self):
        """Mock type conversion: returns self."""
        return self

    def float(self):
        """Mock type conversion: returns self."""
        return self

    def multiply(self, val):
        """Mock multiplication: returns self."""
        return self

    def divide(self, val):
        """Mock division: returns self."""
        return self

    def add(self, val):
        """Mock addition: returns self."""
        return self

    def subtract(self, val):
        """Mock subtraction: returns self."""
        return self

    def hypot(self, val):
        """Mock hypot: returns self."""
        return self

    def date(self):
        """Mock date accessor: returns Date."""
        return Date()

    def set(self, key, val):
        """Mock property setter: stores property and returns self."""
        self._properties[key] = val
        return self

    def get(self, key):
        """Mock property getter: returns stored property or None."""
        return self._properties.get(key)

    def copyProperties(self, source, props=None):
        """Mock copyProperties: returns self."""
        return self

    def updateMask(self, mask):
        """Mock updateMask: returns self."""
        return self

    def bitwiseAnd(self, val):
        """Mock bitwise AND: returns self."""
        return self

    def eq(self, val):
        """Mock equality: returns self."""
        return self

    def neq(self, val):
        """Mock inequality: returns self."""
        return self

    def And(self, other):
        """Mock logical AND: returns self."""
        return self

    def Or(self, other):
        """Mock logical OR: returns self."""
        return self

    def Not(self):
        """Mock logical NOT: returns self."""
        return self

    def lt(self, val):
        """Mock less than: returns self."""
        return self

    def gt(self, val):
        """Mock greater than: returns self."""
        return self

    def lte(self, val):
        """Mock less than or equal: returns self."""
        return self

    def gte(self, val):
        """Mock greater than or equal: returns self."""
        return self

    def expression(self, expression, map):
        """Mock expression: returns self."""
        return self

    def resample(self, mode):
        """Mock resample: returns self."""
        return self

    def reproject(self, crs=None, scale=None, **kwargs):
        """Mock reproject: returns self."""
        return self

    def size(self):
        """Mock size: returns Number(10)."""
        return Number(10)

    def clip(self, geom):
        """Mock clip: returns self."""
        return self

    def buffer(self, dist):
        """Mock buffer: returns self."""
        return self

    def flatten(self):
        """Mock flatten: returns self."""
        return self

    def getDownloadURL(self, *args, **kwargs):
        """Mock download URL: returns dummy URL."""
        return "http://dummy-url.com/data.csv"

    def area(self, *args, **kwargs):
        """Mock area calculation: returns Number(10000)."""
        return Number(10000)

    def focal_mean(self, *args, **kwargs):
        """Mock focal mean: returns self."""
        return self

    def glcmTexture(self, size=None):
        """Mock GLCM texture: returns self."""
        return self

    def qualityMosaic(self, band):
        """Mock quality mosaic: returns self."""
        return self

    def aside(self, func):
        """Mock aside: calls function and returns self."""
        return self

    @staticmethod
    def cat(images):
        """Mock cat: returns Image."""
        return Image()

    @staticmethod
    def constant(val):
        """Mock constant: returns Image."""
        return Image()


class Image(MockEEObject):
    """Mock for ee.Image."""

    def sampleRegions(self, collection, properties=None, scale=None, **kwargs):
        """Mock sampleRegions: returns FeatureCollection."""
        return FeatureCollection()


class ImageCollection(MockEEObject):
    """Mock for ee.ImageCollection."""

    def merge(self, other):
        """Mock merge: returns self."""
        return self

    def combine(self, other):
        """Mock combine: returns self."""
        return self

    def mosaic(self):
        """Mock mosaic: returns Image."""
        return Image()


class FeatureCollection(MockEEObject):
    """Mock for ee.FeatureCollection."""

    def __init__(self, features=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._features = features or []

    def limit(self, max_features):
        """Mock limit: returns self."""
        return self

    def sort(self, property, ascending=True):
        """Mock sort: returns self."""
        return self


class Feature(MockEEObject):
    """Mock for ee.Feature."""

    def __init__(self, geometry=None, properties=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._geometry = geometry
        self._properties = properties or {}


class Geometry(MockEEObject):
    """Mock for ee.Geometry."""

    class Polygon(MockEEObject):
        """Mock for ee.Geometry.Polygon."""

        def __init__(self, coords=None, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._coords = coords or []

    class Point(MockEEObject):
        """Mock for ee.Geometry.Point."""

        def __init__(self, lon=0, lat=0, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._lon = lon
            self._lat = lat


class Projection(MockEEObject):
    """Mock for ee.Projection."""

    def __init__(self, crs="EPSG:4326", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._crs = crs

    def crs(self):
        """Return CRS string."""
        return self._crs


class Filter(MockEEObject):
    """Mock for ee.Filter."""

    @staticmethod
    def lt(name, val):
        """Mock less than filter."""
        return Filter()

    @staticmethod
    def lte(name, val):
        """Mock less than or equal filter."""
        return Filter()

    @staticmethod
    def gt(name, val):
        """Mock greater than filter."""
        return Filter()

    @staticmethod
    def gte(name, val):
        """Mock greater than or equal filter."""
        return Filter()

    @staticmethod
    def eq(name, val):
        """Mock equality filter."""
        return Filter()

    @staticmethod
    def neq(name, val):
        """Mock inequality filter."""
        return Filter()

    @staticmethod
    def calendarRange(start, end, field):
        """Mock calendar range filter."""
        return Filter()

    @staticmethod
    def listContains(name, val):
        """Mock list contains filter."""
        return Filter()

    @staticmethod
    def rangeContains(name, start, end):
        """Mock range contains filter."""
        return Filter()


class Date(MockEEObject):
    """Mock for ee.Date."""

    def __init__(self, date=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._date = date

    def millis(self):
        """Mock millis: returns Number."""
        return Number(1672531200000)  # Dummy timestamp

    def get(self, component):
        """Mock get component: returns Number."""
        return Number(12)  # Dummy value

    def difference(self, other, unit):
        """Mock difference: returns Number."""
        return Number(5)

    def format(self, pattern=None):
        """Mock format: returns string."""
        return "2025-01-01"


class Number(MockEEObject):
    """Mock for ee.Number."""

    def __init__(self, value=0, *args, **kwargs):
        super().__init__(value, *args, **kwargs)

    def getInfo(self):
        """Return the numeric value."""
        return self._value if self._value is not None else 0


class Reducer(MockEEObject):
    """Mock for ee.Reducer."""

    @staticmethod
    def linearFit():
        """Mock linear fit reducer."""
        return Reducer()

    @staticmethod
    def stdDev():
        """Mock standard deviation reducer."""
        return Reducer()

    @staticmethod
    def mean():
        """Mock mean reducer."""
        return Reducer()

    @staticmethod
    def median():
        """Mock median reducer."""
        return Reducer()

    @staticmethod
    def min():
        """Mock min reducer."""
        return Reducer()

    @staticmethod
    def max():
        """Mock max reducer."""
        return Reducer()


class Terrain(MockEEObject):
    """Mock for ee.Terrain."""

    @staticmethod
    def slope(image):
        """Mock slope calculation."""
        return Image()

    @staticmethod
    def aspect(image):
        """Mock aspect calculation."""
        return Image()

    @staticmethod
    def hillshade(image, azimuth=None, elevation=None):
        """Mock hillshade calculation."""
        return Image()


# Module-level functions
def Initialize(credentials=None, opt_url=None):
    """Mock EE initialization."""
    print("Mock EE Initialized")
