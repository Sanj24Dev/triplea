from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "move_generator_cpp",
        ["move_generator.pyx"],
        language="c++",
        extra_compile_args=["-O3", "-std=c++11"],
    )
]

setup(
    name="move_generator_cpp",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'boundscheck': False,
            'wraparound': False,
        }
    ),
)