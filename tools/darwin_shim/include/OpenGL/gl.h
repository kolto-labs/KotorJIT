#pragma once
/* Shape of the legacy <OpenGL/gl.h> (GL 2.1 compatibility) for the entry
   points Hyperstim's overlay and Dear ImGui's GL2 backend use. */
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef unsigned int GLenum;
typedef unsigned int GLbitfield;
typedef unsigned int GLuint;
typedef int GLint;
typedef int GLsizei;
typedef unsigned char GLboolean;
typedef unsigned char GLubyte;
typedef float GLfloat;
typedef double GLdouble;
typedef void GLvoid;
#define GL_FALSE 0
#define GL_TRUE 1
#define GL_NO_ERROR 0
#define GL_TRIANGLES 0x0004
#define GL_ONE 1
#define GL_SRC_ALPHA 0x0302
#define GL_ONE_MINUS_SRC_ALPHA 0x0303
#define GL_FRONT 0x0404
#define GL_BACK 0x0405
#define GL_FRONT_AND_BACK 0x0408
#define GL_CULL_FACE 0x0B44
#define GL_LIGHTING 0x0B50
#define GL_COLOR_MATERIAL 0x0B57
#define GL_DEPTH_TEST 0x0B71
#define GL_STENCIL_TEST 0x0B90
#define GL_VIEWPORT 0x0BA2
#define GL_MODELVIEW 0x1700
#define GL_PROJECTION 0x1701
#define GL_BLEND 0x0BE2
#define GL_SCISSOR_BOX 0x0C10
#define GL_SCISSOR_TEST 0x0C11
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#define GL_TEXTURE_2D 0x0DE1
#define GL_UNSIGNED_BYTE 0x1401
#define GL_UNSIGNED_SHORT 0x1403
#define GL_UNSIGNED_INT 0x1405
#define GL_FLOAT 0x1406
#define GL_RGBA 0x1908
#define GL_FILL 0x1B02
#define GL_SMOOTH 0x1D01
#define GL_VENDOR 0x1F00
#define GL_RENDERER 0x1F01
#define GL_VERSION 0x1F02
#define GL_MODULATE 0x2100
#define GL_TEXTURE_ENV_MODE 0x2200
#define GL_TEXTURE_ENV 0x2300
#define GL_LINEAR 0x2601
#define GL_TEXTURE_MAG_FILTER 0x2800
#define GL_TEXTURE_MIN_FILTER 0x2801
#define GL_TEXTURE_WRAP_S 0x2802
#define GL_TEXTURE_WRAP_T 0x2803
#define GL_CLAMP 0x2900
#define GL_VERTEX_ARRAY 0x8074
#define GL_NORMAL_ARRAY 0x8075
#define GL_COLOR_ARRAY 0x8076
#define GL_TEXTURE_COORD_ARRAY 0x8078
#define GL_POLYGON_MODE 0x0B40
#define GL_SHADE_MODEL 0x0B54
#define GL_TEXTURE_BINDING_2D 0x8069
#define GL_TEXTURE_CUBE_MAP 0x8513
#define GL_CURRENT_PROGRAM 0x8B8D
#define GL_ARRAY_BUFFER 0x8892
#define GL_ENABLE_BIT 0x00002000
#define GL_COLOR_BUFFER_BIT 0x00004000
#define GL_TRANSFORM_BIT 0x00001000
#define GL_ALL_ATTRIB_BITS 0x000fffff
#define GL_CLIENT_ALL_ATTRIB_BITS 0xffffffff
void glBindTexture(GLenum, GLuint);
void glBlendFunc(GLenum, GLenum);
void glColorPointer(GLint, GLenum, GLsizei, const GLvoid*);
void glDeleteTextures(GLsizei, const GLuint*);
void glDisable(GLenum);
void glDisableClientState(GLenum);
void glDrawElements(GLenum, GLsizei, GLenum, const GLvoid*);
void glEnable(GLenum);
void glEnableClientState(GLenum);
void glGenTextures(GLsizei, GLuint*);
GLenum glGetError(void);
void glGetIntegerv(GLenum, GLint*);
const GLubyte* glGetString(GLenum);
void glGetTexEnviv(GLenum, GLenum, GLint*);
void glLoadIdentity(void);
void glMatrixMode(GLenum);
void glOrtho(GLdouble, GLdouble, GLdouble, GLdouble, GLdouble, GLdouble);
void glPixelStorei(GLenum, GLint);
void glPolygonMode(GLenum, GLenum);
void glPopAttrib(void);
void glPopClientAttrib(void);
void glPopMatrix(void);
void glPushAttrib(GLbitfield);
void glPushClientAttrib(GLbitfield);
void glPushMatrix(void);
void glScissor(GLint, GLint, GLsizei, GLsizei);
void glShadeModel(GLenum);
void glTexCoordPointer(GLint, GLenum, GLsizei, const GLvoid*);
void glTexEnvi(GLenum, GLenum, GLint);
void glTexImage2D(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const GLvoid*);
void glTexParameteri(GLenum, GLenum, GLint);
void glVertexPointer(GLint, GLenum, GLsizei, const GLvoid*);
void glViewport(GLint, GLint, GLsizei, GLsizei);
/* GL 1.3+/1.5+/2.0 entry points: exported by OpenGL.framework directly. */
void glActiveTexture(GLenum);
void glClientActiveTexture(GLenum);
void glBindBuffer(GLenum, GLuint);
void glUseProgram(GLuint);
void glBlendFuncSeparate(GLenum, GLenum, GLenum, GLenum);
#ifdef __cplusplus
}
#endif
