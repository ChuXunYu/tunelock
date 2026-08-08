/* qqm_thunk.s - thiscall 汇编 thunk (x86, COFF/PE, tcc)
 *
 * MSVC x86 thiscall 约定:
 *   this 指针通过 ECX 传递
 *   其余参数从右到左压栈
 *   被调者 (callee) 清理栈
 *
 * 每个 thunk: C 侧以 __stdcall 声明(被调者清栈), 这里先把栈上第1个参数(this)
 * 移入 ECX, 然后间接调用真实目标(地址存于 C 全局变量), 最后按栈参数个数 ret。
 */

.text

/* void ctor_t(void* self)  -- 1个栈参数 = 4 字节
 * 对应: ??0EncAndDesMediaFile@@QAE@XZ
 */
.globl _ctor_t@4
_ctor_t@4:
	movl	4(%esp), %ecx		/* this */
	call	*ctor_tgt
	ret	$4

/* int open_t(void* self, wchar_t* path, char b1, char b2)
 * 3个栈参数 = 12 字节
 * 对应: ?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z
 */
.globl _open_t@12
_open_t@12:
	movl	4(%esp), %ecx		/* this */
	call	*open_tgt
	ret	$12

/* unsigned int getSize_t(void* self)  -- 无栈参数
 * 对应: ?GetSize@EncAndDesMediaFile@@QAEKXZ
 */
.globl _getSize_t@4
_getSize_t@4:
	movl	4(%esp), %ecx		/* this */
	call	*getSize_tgt
	ret	$4

/* unsigned int read_t(void* self, void* buf, unsigned size, __int64 offset)
 * 4个栈参数 = 16 字节 (offset 是 8 字节, 但作为两个dword压栈)
 * 对应: ?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z
 */
.globl _read_t@16
_read_t@16:
	movl	4(%esp), %ecx		/* this */
	call	*read_tgt
	ret	$16

/* void dtor_t(void* self)  -- 1个栈参数
 * 对应: ??1EncAndDesMediaFile@@QAE@XZ
 */
.globl _dtor_t@4
_dtor_t@4:
	movl	4(%esp), %ecx		/* this */
	call	*dtor_tgt
	ret	$4

/* 目标地址占位（C 侧运行时赋值） */
.data
.globl _ctor_tgt
ctor_tgt:	.long 0
.globl _open_tgt
open_tgt:	.long 0
.globl _getSize_tgt
getSize_tgt:	.long 0
.globl _read_tgt
read_tgt:	.long 0
.globl _dtor_tgt
dtor_tgt:	.long 0
