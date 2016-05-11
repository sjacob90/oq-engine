#  -*- coding: utf-8 -*-
#  vim: tabstop=4 shiftwidth=4 softtabstop=4

#  Copyright (c) 2016, GEM Foundation

#  OpenQuake is free software: you can redistribute it and/or modify it
#  under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  OpenQuake is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU Affero General Public License
#  along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.
import collections
import numpy

F64 = numpy.float64


# returns a dict imt -> slice
def slicedict(imt_dt):
    n = 0
    slicedic = {}
    for imt in imt_dt.names:
        shp = imt_dt[imt].shape
        n1 = n + shp[0] if shp else 1
        slicedic[imt] = slice(n, n1)
        n = n1
    return slicedic, n


class Imtls(collections.Mapping):
    """
    A small wrapper over an ordered dictionary of intensity measure types
    and levels
    """
    def __init__(self, imtls):
        self.imt_dt = dt = numpy.dtype(
            [(imt, F64, len(imls) if hasattr(imls, '__len__') else 1)
             for imt, imls in sorted(imtls.items())])
        self.slicedic, num_levels = slicedict(dt)
        self.array = numpy.zeros(num_levels, F64)
        for imt, imls in imtls.items():
            self[imt] = imls

    def __getitem__(self, imt):
        return self.array[self.slicedic[imt]]

    def __setitem__(self, imt, array):
        self.array[self.slicedic[imt]] = array

    def __iter__(self):
        for imt in self.imt_dt.names:
            yield imt

    def __len__(self):
        return len(self.imt_dt.names)

    def __repr__(self):
        data = ['%s: %s' % (imt, self.array[imt]) for imt in self]
        return '<Imtls\n%s>' % '\n'.join(data)


class PoeCurve(object):
    """
    This class is a small wrapper over an array of PoEs associated to
    a set of intensity measure types and levels. It provides a few
    class methods to manage a dictionary of curves keyed by an integer
    (the site index) and defines a few operators, including the complement
    operator `~`

    ~p = 1 - p

    and the inclusive or operator `|`

    p = p1 | p2 = ~(~p1 * ~p2)

    Such operators are implemented efficiently at the numpy level, by
    dispatching on the underlying array.

    Here is an example of use:

    >>> imt_dt = numpy.dtype([('PGA', float, 3), ('PGV', float, 2)])
    >>> poe = PoeCurve(imt_dt, numpy.zeros(1, (F64, 5)))
    >>> poe['PGA'] = [0.1, 0.2, 0.3]
    >>> ~(poe | poe) * .5
    <PoeCurve
    PGA: [[[ 0.405  0.32   0.245]]]
    PGV: [[[ 0.5  0.5]]]>
    """
    @classmethod
    def build(cls, imtls, num_gsims, sids, initvalue=0.):
        """
        :param imtls: an :class:`openquake.hazardlib.imt.Imtls` instance
        :param num_gsims: the number of GSIMs
        :returns: a dictionary of PoeCurves
        """
        dic = {}
        for sid in sids:
            array = numpy.empty((len(imtls.array), num_gsims), F64)
            array.fill(initvalue)
            dic[sid] = cls(imtls.slicedic, array)
        return dic

    @classmethod
    def compose(cls, dic1, dic2):
        """
        >>> imtls = Imtls(dict(PGA=[1, 2, 3], PGV=[4, 5]))
        >>> curves1 = PoeCurve.build(imtls, 1, [0, 1], initvalue=.1)
        >>> curves2 = PoeCurve.build(imtls, 1, [1, 2], initvalue=.1)
        >>> dic = PoeCurve.compose(curves1, curves2)
        >>> dic[0]
        <PoeCurve
        PGA: [[[ 0.1  0.1  0.1]]]
        PGV: [[[ 0.1  0.1]]]>
        >>> dic[1]
        <PoeCurve
        PGA: [[[ 0.19  0.19  0.19]]]
        PGV: [[[ 0.19  0.19]]]>
        >>> dic[2]
        <PoeCurve
        PGA: [[[ 0.1  0.1  0.1]]]
        PGV: [[[ 0.1  0.1]]]>
        """
        sids = set(dic1) | set(dic2)
        dic = {}
        for sid in sids:
            curve = dic1.get(sid, 0) | dic2.get(sid, 0)
            if curve:
                dic[sid] = curve
        return dic

    @classmethod
    def multiply(cls, dic1, dic2):
        """
        Multiply two dictionaries of curves
        """
        sids = set(dic1) | set(dic2)
        return {sid: dic1.get(sid, 1) * dic2.get(sid, 1) for sid in sids}

    @classmethod
    def extract(cls, dic, gsim_idx):
        out = {}
        for sid in dic:
            curve = dic[sid]
            array = curve.array[:, gsim_idx].reshape(-1, 1)
            out[sid] = cls(curve.slicedic, array)
        return out

    def __init__(self, slicedic, array):
        self.slicedic = slicedic
        self.array = array

    def __setitem__(self, imt, array):
        self.array[self.slicedic[imt]] = array

    def __getitem__(self, imt):
        return self.array[self.slicedic[imt]]

    def __or__(self, other):
        if other == 0:
            return self
        else:
            return self.__class__(
                self.slicedic, 1. - (1. - self.array) * (1. - other.array))
    __ror__ = __or__

    def __mul__(self, other):
        if isinstance(other, self.__class__):
            return self.__class__(self.slicedic, self.array * other.array)
        elif other == 1:
            return self
        else:
            return self.__class__(self.slicedic, self.array * other)
    __rmul__ = __mul__

    def __invert__(self):
        return self.__class__(self.slicedic, 1. - self.array)

    def __nonzero__(self):
        return bool(self.array.sum())

    def __repr__(self):
        data = ['%s: %s' % (imt, self[imt]) for imt in sorted(self.slicedic)]
        return '<PoeCurve\n%s>' % '\n'.join(data)
