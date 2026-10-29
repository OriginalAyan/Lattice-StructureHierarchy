from chimerax.core.toolshed import BundleAPI


class _StructureHierarchyAPI(BundleAPI):
    api_version = 1

    @staticmethod
    def start_tool(session, bi, ti):
        if ti.name != "Structure Hierarchy":
            raise ValueError(f"Unknown tool name: {ti.name}")
        from chimerax.core import tools
        from .tool import StructureHierarchyTool
        return tools.get_singleton(session, StructureHierarchyTool, ti.name, create=True)

    @staticmethod
    def initialize(session, bundle_info):
        """Start-up hook (customInit): restore/save Important marks without the panel open."""
        from . import persist
        persist.initialize(session)

    @staticmethod
    def finish(session, bundle_info):
        from . import persist
        persist.finish(session)

    @staticmethod
    def register_command(bi, ci, logger):
        from chimerax.core.commands import register
        if ci.name == "hierarchy":
            from .commands import hierarchy_desc, cmd_hierarchy
            desc = hierarchy_desc
            func = cmd_hierarchy
        elif ci.name == "hierarchy marks":
            from .commands import hierarchy_marks_desc, cmd_hierarchy_marks
            desc = hierarchy_marks_desc()
            func = cmd_hierarchy_marks
        else:
            raise ValueError(f"Unknown command name: {ci.name}")
        if desc.synopsis is None:
            desc.synopsis = ci.synopsis
        register(ci.name, desc, func, logger=logger)

    @staticmethod
    def get_class(class_name):
        if class_name == "StructureHierarchyTool":
            from .tool import StructureHierarchyTool
            return StructureHierarchyTool
        raise ValueError(f"Unknown class name '{class_name}'")


bundle_api = _StructureHierarchyAPI()
