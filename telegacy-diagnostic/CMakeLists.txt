cmake_minimum_required(VERSION 3.24)
project(TelegacyDiagnostic LANGUAGES C CXX RC)

if(NOT MSVC)
    message(FATAL_ERROR "This diagnostic build currently targets MSVC on Windows.")
endif()

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
    message(FATAL_ERROR "Telegacy is a Win32 application. Configure with -A Win32.")
endif()

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED OFF)

set(SOURCES
    src/calculations.cpp
    src/conversions.cpp
    src/helpers.cpp
    src/message.cpp
    src/offsets.cpp
    src/procs.cpp
    src/response.cpp
    src/telegacy.cpp
    third_party/qrcodegen/qrcodegen.c
    res/resources.rc
)

add_executable(telegacy-diagnostic WIN32 ${SOURCES})

target_include_directories(telegacy-diagnostic PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/res"
    "${CMAKE_CURRENT_SOURCE_DIR}/third_party/qrcodegen"
)

find_path(TOMCRYPT_INCLUDE_DIR NAMES tomcrypt.h REQUIRED)
find_library(TOMCRYPT_LIBRARY NAMES tomcrypt libtomcrypt REQUIRED)

find_path(TOMMATH_INCLUDE_DIR NAMES tommath.h REQUIRED)
find_library(TOMMATH_LIBRARY NAMES tommath libtommath REQUIRED)

find_path(MINIZ_INCLUDE_DIR NAMES miniz.h PATH_SUFFIXES miniz REQUIRED)
find_path(RLOTTIE_INCLUDE_DIR NAMES rlottie.h REQUIRED)

if(NOT VCPKG_INSTALLED_DIR OR NOT VCPKG_TARGET_TRIPLET)
    message(FATAL_ERROR "rlottie requires the vcpkg-installed target tree.")
endif()

find_library(RLOTTIE_LIBRARY_RELEASE
    NAMES rlottie
    PATHS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/lib"
    NO_DEFAULT_PATH
    REQUIRED
)

find_library(RLOTTIE_LIBRARY_DEBUG
    NAMES rlottie
    PATHS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/debug/lib"
    NO_DEFAULT_PATH
    REQUIRED
)

find_path(WEBP_INCLUDE_DIR NAMES webp/decode.h REQUIRED)
find_library(WEBP_LIBRARY NAMES webp libwebp REQUIRED)
find_library(SHARPYUV_LIBRARY NAMES sharpyuv libsharpyuv)

find_path(JPEG_INCLUDE_DIR NAMES jpeglib.h REQUIRED)
find_library(JPEG_LIBRARY NAMES jpeg libjpeg REQUIRED)

target_include_directories(telegacy-diagnostic PRIVATE
    "${TOMCRYPT_INCLUDE_DIR}"
    "${TOMMATH_INCLUDE_DIR}"
    "${MINIZ_INCLUDE_DIR}"
    "${WEBP_INCLUDE_DIR}"
    "${JPEG_INCLUDE_DIR}"
    "${RLOTTIE_INCLUDE_DIR}"
)

target_compile_definitions(telegacy-diagnostic PRIVATE
    WIN32
    _WINDOWS
    UNICODE
    _UNICODE
    LTM_DESC
    _CRT_SECURE_NO_WARNINGS
    _CRT_NON_CONFORMING_SWPRINTFS
    RLOTTIE_BUILD=0
)

target_compile_options(telegacy-diagnostic PRIVATE
    /W3
    /EHsc
    /Zc:forScope-
    /bigobj
)

set_property(TARGET telegacy-diagnostic PROPERTY
    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"
)

target_link_libraries(telegacy-diagnostic PRIVATE
    "${TOMCRYPT_LIBRARY}"
    "${TOMMATH_LIBRARY}"
    optimized "${RLOTTIE_LIBRARY_RELEASE}"
    debug "${RLOTTIE_LIBRARY_DEBUG}"
    "${WEBP_LIBRARY}"
    "${JPEG_LIBRARY}"

    kernel32
    user32
    gdi32
    comdlg32
    advapi32
    shell32
    shlwapi
    ole32
    oleaut32
    uuid
    wsock32
    comctl32
    winmm
    version
    htmlhelp
    winspool
    odbc32
    odbccp32
    bcrypt
)

if(SHARPYUV_LIBRARY)
    target_link_libraries(telegacy-diagnostic PRIVATE "${SHARPYUV_LIBRARY}")
endif()

target_compile_options(telegacy-diagnostic PRIVATE
    $<$<CONFIG:RelWithDebInfo>:/Zi>
)
target_link_options(telegacy-diagnostic PRIVATE
    $<$<CONFIG:RelWithDebInfo>:/DEBUG:FULL>
    $<$<CONFIG:RelWithDebInfo>:/MAP:${CMAKE_BINARY_DIR}/telegacy-diagnostic.map>
)

set_target_properties(telegacy-diagnostic PROPERTIES
    OUTPUT_NAME "telegacy-diagnostic"
)
