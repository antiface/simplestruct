"""Unit tests for fields.py."""


import unittest

from simplestruct.struct import *
from simplestruct.fields import *


class FieldsCase(unittest.TestCase):
    
    def test_TypedField(self):
        # Non-sequence case.
        class Foo(Struct):
            bar = TypedField(int)
        f = Foo(1)
        with self.assertRaises(TypeError):
            Foo('a')
        
        # Sequence case.
        class Foo(Struct):
            bar = TypedField(int, seq=True)
        f = Foo([1, 2])
        self.assertEqual(f.bar, ((1, 2)))
        with self.assertRaises(TypeError):
            Foo([1, 'a'])
        
        # Nodups sequence.
        class Foo(Struct):
            bar = TypedField(int, seq=True, nodups=True)
        Foo([1, 2])
        with self.assertRaises(TypeError):
            Foo([1, 2, 1])
        
        # Optional case.
        class Foo(Struct):
            _immutable = False
            bar = TypedField(int, opt=True)
        f1 = Foo()
        f2 = Foo(5)
        f2.bar = None
        self.assertEqual(f1, f2)

if __name__ == '__main__':
    unittest.main()
