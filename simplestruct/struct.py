"""Core framework for Struct, its metaclass, and field descriptors."""


__all__ = [
    'Field',
    'MetaStruct',
    'Struct',
]


from collections import OrderedDict, Counter
from functools import reduce
from inspect import Signature, Parameter


def hash_seq(seq):
    """Given a sequence of hash values, return a combined xor'd hash."""
    return reduce(lambda x, y: x ^ y, seq, 0)


class Field:
    
    """Descriptor for declaring fields on Structs.
    
    Writing to a field will fail with AttributeError if the Struct
    is immutable and has finished initializing.
    
    Subclasses may override __set__() to implement type restrictions
    or coercion, and may override eq() and hash() to implement custom
    equality semantics.
    """
    
    def __init__(self):
        # name is the attribute name through which this field is
        # accessed from the Struct. This will be set automatically
        # by MetaStruct.
        self.name = None
    
    def copy(self):
        # This is used by MetaStruct to get a fresh instance
        # of the field for each of its occurrences.
        return type(self)()
    
    def __get__(self, inst, value):
        if inst is None:
            raise AttributeError('Cannot retrieve field from class')
        return inst.__dict__[self.name]
    
    def __set__(self, inst, value):
        if inst._immutable and inst._initialized:
            raise AttributeError('Struct is immutable')
        inst.__dict__[self.name] = value
    
    def eq(self, val1, val2):
        """Compare two values for this field."""
        return val1 == val2
    
    def hash(self, val):
        """Hash a value for this field."""
        return hash(val)


class MetaStruct(type):
    
    """Metaclass for Structs.
    
    Upon class definition (of a new Struct subtype), set the class
    attribute _struct to be a tuple of the Field descriptors, in
    declaration order. If the class has attribute _inherit_fields
    and it evaluates to true, also include fields of base classes.
    (Names of inherited fields must not collide with other inherited
    fields or this class's fields.) Set class attribute _signature
    to be an inspect.Signature object to facilitate instantiation.
    
    Upon instantiation of a Struct subtype, set the instance's
    _initialized attribute to True after __init__() returns.
    """
    
    # Use OrderedDict to preserve Field declaration order.
    @classmethod
    def __prepare__(mcls, name, bases, **kargs):
        return OrderedDict()
    
    # Construct the _struct attribute on the new class.
    def __new__(mcls, clsname, bases, namespace, **kargs):
        fields = []
        # If inheriting, gather fields from base classes.
        if namespace.get('_inherit_fields', False):
            for b in bases:
                if isinstance(b, MetaStruct):
                    fields += b._struct
        # Gather fields from this class's namespace.
        for fname, f in namespace.items():
            # Using the Field class directly (or one of its subclasses)
            # is shorthand for making a Field instance with no args.
            if isinstance(f, type) and issubclass(f, Field):
                f = f()
            if isinstance(f, Field):
                # Fields need to be copied in case they're used
                # in multiple places (in this class or others).
                f = f.copy()
                f.name = fname
                fields.append(f)
            namespace[fname] = f
        # Ensure no name collisions.
        fnames = Counter(f.name for f in fields)
        collided = [k for k in fnames if fnames[k] > 1]
        if len(collided) > 0:
            raise AttributeError(
                'Struct {} has colliding field name(s): {}'.format(
                clsname, ', '.join(collided)))
        
        cls = super().__new__(mcls, clsname, bases, dict(namespace), **kargs)
        
        cls._struct = tuple(fields)
        
        cls._signature = Signature(
            parameters=[Parameter(f.name, Parameter.POSITIONAL_OR_KEYWORD)
                        for f in cls._struct])
        
        return cls
    
    # Mark the class as _initialized after construction.
    def __call__(mcls, *args, **kargs):
        inst = super().__call__(*args, **kargs)
        inst._initialized = True
        return inst


class Struct(metaclass=MetaStruct):
    
    """Base class for Structs.
    
    Declare fields by assigning class attributes to an instance of
    the descriptor Field or one of its subclasses. As a convenience,
    assigning to the Field (sub)class itself is also permitted.
    The fields become the positional arguments to the class's
    constructor. Construction via keyword argument is also allowed,
    following normal Python parameter passing rules.
    
    If class attribute _inherit_fields is defined and evaluates to
    true, the fields of each base class are prepended to this class's
    list of fields in left-to-right order.
    
    A subclass may define __init__() to customize how fields are
    initialized, or to set other non-field attributes. If the class
    attribute _immutable evaluates to true, assigning to fields is
    disallowed once the last subclass's __init__() finishes.
    
    Structs may be pickled. Upon unpickling, __init__() will be
    called.
    
    Structs support structural equality. Hashing is allowed only
    for immutable Structs and after they are initialized.
    
    The methods _asdict() and _replace() behave as they do for
    collections.namedtuple.
    """
    
    _immutable = True
    """Flag for whether to allow reassignment to fields after
    construction. Override with False in subclass to allow.
    """
    
    def __new__(cls, *args, **kargs):
        inst = super().__new__(cls)
        # _initialized is read during field initialization.
        inst._initialized = False
        
        try:
            boundargs = cls._signature.bind(*args, **kargs)
            for f in cls._struct:
                setattr(inst, f.name, boundargs.arguments[f.name])
        except TypeError as exc:
            raise TypeError('Error constructing ' + cls.__name__) from exc
        
        return inst
    
    def _fmt_helper(self, fmt):
        return '{}({})'.format(
            self.__class__.__name__,
            ', '.join('{}={}'.format(f.name, fmt(getattr(self, f.name)))
                      for f in self._struct))
    
    def __str__(self):
        return self._fmt_helper(str)
    def __repr__(self):
        return self._fmt_helper(repr)
    
    def __eq__(self, other):
        # Two Struct instances are equal if one of their classes
        # is a subclass of the other, and if the field schema
        # is the same.
        #
        # An alternative semantics would be to require that the types
        # be exactly the same. I'm undecided on whether that would be
        # better.
        
        # We're only responsible for a decision if our class is at
        # least as derived as the other guy's class. Otherwise punt
        # to the other guy's __eq__().
        if not isinstance(self, other.__class__):
            return NotImplemented
        
        # If the fields are not exactly the same, including order,
        # we're not equal.
        if self._struct != other._struct:
            return False
        
        return all(f.eq(getattr(self, f.name), getattr(other, f.name))
                   for f in self._struct)
    
    def __hash__(self):
        if not self._immutable:
            raise TypeError('Cannot hash mutable Struct {}'.format(
                            self.__class__.__name__))
        if not self._initialized:
            raise TypeError('Cannot hash uninitialized Struct {}'.format(
                            self.__class__.__name__))
        return hash_seq(f.hash(getattr(self, f.name))
                        for f in self._struct)
    
    def __len__(self):
        return len(self._struct)
    
    def __iter__(self):
        return (getattr(self, f.name) for f in self._struct)
    
    def __reduce_ex__(self, protocol):
        # We use __reduce_ex__() rather than __getnewargs__() so that
        # the metaclass's __call__() will still run. This is needed to
        # trigger the user-defined __init__() and to set _immutable to
        # False.
        return (self.__class__, tuple(getattr(self, f.name)
                                      for f in self._struct))
    
    def _asdict(self):
        """Return an OrderedDict of the fields."""
        return OrderedDict((f.name, getattr(self, f.name))
                           for f in self._struct)
    
    def _replace(self, **kargs):
        """Return a copy of this Struct with the same fields except
        with the changes specified by kargs.
        """
        fields = {f.name: getattr(self, f.name)
                  for f in self._struct}
        fields.update(kargs)
        return type(self)(**fields)
