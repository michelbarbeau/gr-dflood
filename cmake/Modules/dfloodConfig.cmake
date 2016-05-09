INCLUDE(FindPkgConfig)
PKG_CHECK_MODULES(PC_DFLOOD dflood)

FIND_PATH(
    DFLOOD_INCLUDE_DIRS
    NAMES dflood/api.h
    HINTS $ENV{DFLOOD_DIR}/include
        ${PC_DFLOOD_INCLUDEDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/include
          /usr/local/include
          /usr/include
)

FIND_LIBRARY(
    DFLOOD_LIBRARIES
    NAMES gnuradio-dflood
    HINTS $ENV{DFLOOD_DIR}/lib
        ${PC_DFLOOD_LIBDIR}
    PATHS ${CMAKE_INSTALL_PREFIX}/lib
          ${CMAKE_INSTALL_PREFIX}/lib64
          /usr/local/lib
          /usr/local/lib64
          /usr/lib
          /usr/lib64
)

INCLUDE(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(DFLOOD DEFAULT_MSG DFLOOD_LIBRARIES DFLOOD_INCLUDE_DIRS)
MARK_AS_ADVANCED(DFLOOD_LIBRARIES DFLOOD_INCLUDE_DIRS)

