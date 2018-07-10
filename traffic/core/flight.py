import logging
from datetime import datetime, timedelta
from typing import Iterator, Optional, Set, Tuple, Union

import numpy as np

import pandas as pd
from cartopy.mpl.geoaxes import GeoAxesSubplot
from shapely.geometry import LineString, base

from ..core.time import time_or_delta, timelike, to_datetime
from .mixins import DataFrameMixin, GeographyMixin, ShapelyMixin


def _split(data: pd.DataFrame, value, unit) -> Iterator[pd.DataFrame]:
    diff = data.timestamp.diff().values
    if diff.max() > np.timedelta64(value, unit):
        yield from _split(data.iloc[: diff.argmax()], value, unit)
        yield from _split(data.iloc[diff.argmax():], value, unit)
    else:
        yield data


class Flight(DataFrameMixin, ShapelyMixin, GeographyMixin):
    """Flight is the basic class associated to an aircraft itinerary.

    A Flight is supposed to start at takeoff and end after landing, taxiing and
    parking.

    If the current structure seems to contain many flights, warnings may be
    raised.
    """

    def __add__(self, other):
        """Concatenates two Flight objects in the same Traffic structure."""
        if other == 0:
            # useful for compatibility with sum() function
            return self

        # keep import here to avoid recursion
        from .traffic import Traffic
        return Traffic.from_flights([self, other])

    def __radd__(self, other):
        """Concatenates two Flight objects in the same Traffic structure."""
        return self + other

    def _info_html(self) -> str:
        title = f"<b>Flight {self.callsign}</b>"
        if self.number is not None:
            title += f" / {self.number}"
        if self.flight_id is not None:
            title += f" ({self.flight_id})"

        title += "<ul>"
        title += f"<li><b>aircraft:</b> {self.aircraft}</li>"
        if self.origin is not None:
            title += f"<li><b>origin:</b> {self.origin} ({self.start})</li>"
        else:
            title += f"<li><b>origin:</b> {self.start}</li>"
        if self.destination is not None:
            title += f"<li><b>destination:</b> {self.destination} "
            title += f"({self.stop})</li>"
        else:
            title += f"<li><b>destination:</b> {self.stop}</li>"
        title += "</ul>"
        return title

    def _repr_html_(self) -> str:
        title = self._info_html()
        no_wrap_div = '<div style="white-space: nowrap">{}</div>'
        return title + no_wrap_div.format(self._repr_svg_())

    @property
    def timestamp(self) -> Iterator[pd.Timestamp]:
        """Iterates the timestamp column of the DataFrame."""
        yield from self.data.timestamp

    @property
    def start(self) -> pd.Timestamp:
        """Returns the minimum timestamp value of the DataFrame."""
        return min(self.timestamp)

    @property
    def stop(self) -> pd.Timestamp:
        """Returns the maximum timestamp value of the DataFrame."""
        return max(self.timestamp)

    @property
    def callsign(self) -> Union[str, Set[str]]:
        """Returns the unique callsign value(s) of the DataFrame."""
        tmp = set(self.data.callsign)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several callsigns for one flight, consider splitting")
        return tmp

    @property
    def number(self) -> Optional[Union[str, Set[str]]]:
        """Returns the unique number value(s) of the DataFrame."""
        if "number" not in self.data.columns:
            return None
        tmp = set(self.data.number)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several numbers for one flight, consider splitting")
        return tmp

    @property
    def icao24(self) -> Union[str, Set[str]]:
        """Returns the unique icao24 value(s) of the DataFrame.

        icao24 is a unique identifier associated to a transponder.
        """
        tmp = set(self.data.icao24)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several icao24 for one flight, consider splitting")
        return tmp

    @property
    def flight_id(self) -> Optional[Union[str, Set[str]]]:
        """Returns the unique flight_id value(s) of the DataFrame.

        If you know how to split flights, you may want to append such a column
        in the DataFrame.
        """
        if "flight_id" not in self.data.columns:
            return None
        tmp = set(self.data.flight_id)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several ids for one flight, consider splitting")
        return tmp

    @property
    def origin(self) -> Optional[Union[str, Set[str]]]:
        """Returns the unique origin value(s) of the DataFrame.

        The origin airport is mostly represented as a ICAO or a IATA code.
        """
        if "origin" not in self.data.columns:
            return None
        tmp = set(self.data.origin)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several origins for one flight, consider splitting")
        return tmp

    @property
    def destination(self) -> Optional[Union[str, Set[str]]]:
        """Returns the unique destination value(s) of the DataFrame.

        The destination airport is mostly represented as a ICAO or a IATA code.
        """
        if "destination" not in self.data.columns:
            return None
        tmp = set(self.data.destination)
        if len(tmp) == 1:
            return tmp.pop()
        logging.warn("Several destinations for one flight, consider splitting")
        return tmp

    @property
    def aircraft(self) -> Optional[str]:
        if not isinstance(self.icao24, str):
            return None
        from ..data import aircraft as acdb

        ac = acdb[self.icao24]
        if ac.shape[0] != 1:
            return self.icao24
        else:
            return f"{self.icao24} / {ac.iloc[0].regid} ({ac.iloc[0].mdl})"

    @property
    def registration(self) -> Optional[str]:
        from ..data import aircraft as acdb

        if not isinstance(self.icao24, str):
            return None
        ac = acdb[self.icao24]
        if ac.shape[0] != 1:
            return None
        return ac.iloc[0].regid

    @property
    def coords(self) -> Iterator[Tuple[float, float, float]]:
        """Iterates on longitudes, latitudes and altitudes.

        If the baro_altitude field is present, it is preferred over altitude
        """
        data = self.data[self.data.longitude.notnull()]
        altitude = (
            "baro_altitude"
            if "baro_altitude" in self.data.columns
            else "altitude"
        )
        yield from zip(data["longitude"], data["latitude"], data[altitude])

    @property
    def xy_time(self) -> Iterator[Tuple[float, float, float]]:
        """Iterates on longitudes, latitudes and timestamps."""
        iterator = iter(zip(self.coords, self.timestamp))
        while True:
            next_ = next(iterator, None)
            if next_ is None:
                return
            coords, time = next_
            yield (coords[0], coords[1], time.to_pydatetime().timestamp())

    @property
    def linestring(self) -> Optional[LineString]:
        coords = list(self.coords)
        if len(coords) < 2:
            return None
        return LineString(coords)

    @property
    def shape(self) -> Optional[LineString]:
        return self.linestring

    def airborne(self) -> 'Flight':
        """Returns the airborne part of the Flight.

        The airborne part is determined by null values on the altitude (or
        baro_altitude if present) column.
        """
        altitude = (
            "baro_altitude"
            if "baro_altitude" in self.data.columns
            else "altitude"
        )
        return self.__class__(self.data[self.data[altitude].notnull()])
    
    def filtering(self, features, kernels_size):
    
        default_kernels_size = {
            'altitude': 17, 'track': 5, 'ground_speed': 5, 
            'longitude': 15, 'latitude': 15, 'cas': 5, 'tas': 5
        }

        def prepare(df, feature, kernel_size=5):
            """ Prepare data by feature for the filtering

            Our filtering works as follow: given a signal y over time,
            we first apply a low pass filter (e.g medfilt) which give y_m. 
            epsilon2 is the difference between y and y_m squaring
            we aplpy an other first order low pass filter (e.g medfilt) which give sigma

            `flight`: the flight to filtered
            `feature`: column to filtered
            `kernel_size`: size of the kernel for the medfilt

            Errors may raised if the kernel_size is too large
            """
            f = pd.DataFrame(np.nan, index=df.index, columns=['timestamp', 'y', 'y_m', 'epsilon2', 'sigma'])
            f['timestamp'] = df['timestamp']
            f['y'] = df[feature]
            f['y_m'] = medfilt(f['y'], kernel_size)
            f['epsilon2'] = (f['y'] - f['y_m'])**2
            f['sigma'] = np.sqrt(medfilt(f.epsilon2, kernel_size))

            return f

        def decision(df):
            """ Decision accept/reject data points in the signal

            If the point is accepted given the criterion, the value is not alter
            Otherwise it is as follow: ...
            """
            mean_epsilon2, values = df.epsilon2.mean(), []

            for idx, val in enumerate(df.values):
                row = df.iloc[idx]
                y, y_m, sigma, epsilon2 = row['y'], row['y_m'], row['sigma'], row['epsilon2']

                if epsilon2 > mean_epsilon2:
                    borne_inf = y_m - sigma
                    borne_sup = y_m + sigma
                    if y < borne_inf:
                        values.append(borne_inf)
                    elif y > borne_sup:
                        values.append(borne_sup)        
                    else:
                        values.append(y) # maybe mean t-1 t+1
                else:
                    values.append(y)

            return values

        self.data = self.data.sort_values(by='timestamp')

        if features == None:
            features = []
            for feature in self.data.columns:
                dtype = self.data[feature].dtype
                if dtype == np.float32 or dtype == np.float64 or dtype == np.int32 or dtype == np.int64:
                    features.append(feature)

        if kernels_size == None:
            kernels_size = [0 for _ in range(len(features))]
            for idx, feature in enumerate(features):
                kernels_size[idx] = default_kernels_size.get(feature, 17)

        for feature, kernel_size in zip(features, kernels_size):

            # Prepare flight for the filtering
            df = prepare(self.data[['timestamp', feature]], feature, kernel_size)

            # Decision accept/reject for all data point in the time series
            self.data.iloc[:][feature] = decision(df)

        return self
    
    
    
    # -- Interpolation and resampling --

    def split(self, value: int = 10, unit: str = "m") -> Iterator['Flight']:
        """Splits Flights in several legs.

        By default, Flights are split if no value is given during 10 minutes.
        """
        for data in _split(self.data, value, unit):
            yield self.__class__(data)

    def resample(self, rule: str = "1s") -> 'Flight':
        """Resamples a Flight at a one point per second rate. """
        data = (
            self.data.assign(start=self.start, stop=self.stop)
            .set_index("timestamp")
            .resample(rule)
            .interpolate()
            .reset_index()
            .fillna(method="pad")
        )
        return self.__class__(data)

    def at(self, time: timelike) -> pd.core.series.Series:
        index = to_datetime(time)
        return self.data.set_index("timestamp").loc[index]

    def between(self, before: timelike, after: time_or_delta) -> "Flight":
        before = to_datetime(before)
        if isinstance(after, timedelta):
            after = before + after
        else:
            after = to_datetime(after)

        t: np.ndarray = np.stack(self.timestamp)
        index = np.where((before < t) & (t < after))
        return self.__class__(self.data.iloc[index])

    # -- Geometry operations --

    def clip(
        self, shape: base.BaseGeometry
    ) -> Union[None, "Flight", Iterator["Flight"]]:

        linestring = LineString(list(self.airborne().xy_time))
        intersection = linestring.intersection(shape)

        if intersection.is_empty:
            return None

        if isinstance(intersection, LineString):
            times = list(
                datetime.fromtimestamp(t)
                for t in np.stack(intersection.coords)[:, 2]
            )
            return self.__class__(
                self.data[
                    (self.data.timestamp >= min(times))
                    & (self.data.timestamp <= max(times))
                ]
            )

        def _clip_generator():
            for segment in intersection:
                times = list(
                    datetime.fromtimestamp(t)
                    for t in np.stack(segment.coords)[:, 2]
                )
                yield self.__class__(
                    self.data[
                        (self.data.timestamp >= min(times))
                        & (self.data.timestamp <= max(times))
                    ]
                )

        return (leg for leg in _clip_generator())

    # -- Visualisation --

    def plot(self, ax: GeoAxesSubplot, **kwargs) -> None:
        if "projection" in ax.__dict__ and "transform" not in kwargs:
            from cartopy.crs import PlateCarree

            kwargs["transform"] = PlateCarree()
        if self.shape is not None:
            ax.plot(*self.shape.xy, **kwargs)
