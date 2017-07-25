from . import Analysis, register_analysis
from .. import SIM_PROCEDURES

import logging
l = logging.getLogger('angr.analyses.callee_cleanup_finder')

class CalleeCleanupFinder(Analysis):
    def __init__(self, starts=None, hook_all=False):
        self.results = {}

        if starts is None:
            starts = [imp.resolvedby.rebased_addr for imp in self.project.loader.main_object.imports.itervalues()]

        for addr in starts:
            if self.project.is_hooked(addr):
                continue
            with self._resilience():
                size = self.analyze(addr)
                if size is None:
                    l.info("Couldn't find return for function at %#x", addr)
                else:
                    self.results[addr] = size

        if hook_all:
            for addr, size in self.results.iteritems():
                if size % self.project.arch.bytes != 0:
                    l.error("Function at %#x has a misaligned return?", addr)
                    continue
                args = size / self.project.arch.bytes
                cc = self.project.factory.cc_from_arg_kinds([False]*args)
                cc.CALLEE_CLEANUP = True
                sym = self.project.loader.find_symbol(addr)
                name = sym.name if sym is not None else None
                self.project.hook(addr, SIM_PROCEDURES['stubs']['ReturnUnconstrained'](cc=cc, display_name=name, is_stub=True))

    def analyze(self, addr):
        seen = set()
        todo = [addr]

        while todo:
            addr = todo.pop(0)
            seen.add(addr)
            irsb = self.project.factory.block(addr, opt_level=0).vex
            if irsb.jumpkind == 'Ijk_Ret':
                # got it!
                for stmt in reversed(irsb.statements):
                    if stmt.tag == 'Ist_IMark':
                        l.error("VERY strange return instruction at %#x...", addr)
                        break
                    if stmt.tag == 'Ist_WrTmp':
                        if stmt.data.tag == 'Iex_Binop':
                            if stmt.data.op.startswith('Iop_Add'):
                                return stmt.data.args[1].con.value - self.project.arch.bytes
            elif irsb.jumpkind == 'Ijk_Call':
                if addr + irsb.size not in seen:
                    todo.append(addr + irsb.size)
            else:
                todo.extend(irsb.constant_jump_targets - seen)

        return None

register_analysis(CalleeCleanupFinder, 'CalleeCleanupFinder')
