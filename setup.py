from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "combat_move_gen",
        ["combat_move_gen.pyx"],
        language="c++",
        extra_compile_args=["-O3", "-std=c++11"],
    )
]

setup(
    name="combat_move_gen",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'boundscheck': False,
            'wraparound': False,
        }
    ),
)