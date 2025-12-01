"""Function/tool calling definitions for AI assistant"""

import logging
from typing import Dict, Any, Callable, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Parameter definition for a tool"""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None


class ToolDefinition(BaseModel):
    """Definition of a callable tool/function"""
    name: str
    description: str
    parameters: List[ToolParameter]
    function: Optional[Callable] = None

    class Config:
        arbitrary_types_allowed = True

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format"""
        properties = {}
        required = []

        for param in self.parameters:
            prop_def = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop_def["enum"] = param.enum

            properties[param.name] = prop_def

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }


class ToolRegistry:
    """Registry for available tools/functions"""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        """Register a tool"""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_all(self) -> List[ToolDefinition]:
        """Get all registered tools"""
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get all tools in OpenAI format"""
        return [tool.to_openai_format() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        if not tool.function:
            raise ValueError(f"Tool {name} has no implementation")

        logger.info(f"Executing tool: {name} with args: {arguments}")

        # Handle both sync and async functions
        import inspect
        if inspect.iscoroutinefunction(tool.function):
            return await tool.function(**arguments)
        else:
            return tool.function(**arguments)


def tool(name: str, description: str, parameters: List[ToolParameter]):
    """Decorator to register a function as a tool"""
    def decorator(func: Callable) -> Callable:
        tool_def = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            function=func
        )
        # Tools will be registered when imported
        func._tool_definition = tool_def
        return func
    return decorator


# Define available tools for HomeSight
def get_default_tools() -> ToolRegistry:
    """Get default tool registry with HomeSight tools"""
    registry = ToolRegistry()

    # Tool: Get device history
    registry.register(ToolDefinition(
        name="get_device_history",
        description="Retrieve historical metrics and incidents for a specific device",
        parameters=[
            ToolParameter(
                name="device_id",
                type="string",
                description="The unique identifier of the device"
            ),
            ToolParameter(
                name="hours",
                type="number",
                description="Number of hours of history to retrieve",
                required=False
            )
        ]
    ))

    # Tool: Reset device
    registry.register(ToolDefinition(
        name="reset_device",
        description="Reset a device to clear errors or reinitialize it",
        parameters=[
            ToolParameter(
                name="device_id",
                type="string",
                description="The unique identifier of the device to reset"
            )
        ]
    ))

    # Tool: Schedule technician
    registry.register(ToolDefinition(
        name="schedule_technician",
        description="Schedule a technician visit for device maintenance or repair",
        parameters=[
            ToolParameter(
                name="device_id",
                type="string",
                description="The device requiring service"
            ),
            ToolParameter(
                name="issue_description",
                type="string",
                description="Description of the issue"
            ),
            ToolParameter(
                name="priority",
                type="string",
                description="Priority level",
                enum=["low", "medium", "high", "urgent"]
            )
        ]
    ))

    # Tool: Update device settings
    registry.register(ToolDefinition(
        name="update_device_settings",
        description="Update configuration settings for a device",
        parameters=[
            ToolParameter(
                name="device_id",
                type="string",
                description="The device to configure"
            ),
            ToolParameter(
                name="settings",
                type="object",
                description="Settings to update (key-value pairs)"
            )
        ]
    ))

    # Tool: Search knowledge base
    registry.register(ToolDefinition(
        name="search_knowledge_base",
        description="Search the RAG knowledge base for device documentation and troubleshooting guides",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                description="Search query for documentation"
            ),
            ToolParameter(
                name="device_type",
                type="string",
                description="Optional device type to filter results",
                required=False
            )
        ]
    ))

    # Tool: Get current incidents
    registry.register(ToolDefinition(
        name="get_current_incidents",
        description="Get all current active incidents and alerts in the home. Use this when user asks about the status of their home, specific rooms, or devices.",
        parameters=[
            ToolParameter(
                name="location",
                type="string",
                description="Optional location filter (e.g., 'basement', 'kitchen')",
                required=False
            ),
            ToolParameter(
                name="severity",
                type="string",
                description="Optional severity filter",
                enum=["low", "medium", "high", "critical"],
                required=False
            )
        ]
    ))

    # Tool: Get zone/room info
    registry.register(ToolDefinition(
        name="get_zone_info",
        description="Get detailed information about a specific zone/room including its devices, attributes (floor type, HVAC, plumbing, etc.), and current status. Use this when user asks about a specific room like 'tell me about my basement' or 'what's in the kitchen'.",
        parameters=[
            ToolParameter(
                name="zone_name",
                type="string",
                description="The name or ID of the zone/room (e.g., 'basement', 'kitchen', 'living-room')"
            )
        ]
    ))

    return registry
