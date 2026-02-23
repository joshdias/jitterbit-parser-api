import json


class JitterbitProjectParser:
    def __init__(self, project_json: dict):
        self.project_json = project_json
        self.project = project_json.get("project", {})
        self.component_index = self._build_component_index()

    def _build_component_index(self) -> dict:
        components = self.project.get("components", [])
        return {
            component.get("id"): component
            for component in components
            if isinstance(component, dict) and "id" in component
        }

    def parse(self) -> dict:
        return {
            "project_name": self.project.get("name"),
            "workflows": self._parse_workflows(),
            "orphan_operations": self._find_orphan_operations(),
            "transformations": self._parse_all_transformations(),
        }

    def _parse_workflows(self) -> list:
        workflows = self.project.get("workflows") or []
        parsed_workflows = []

        for workflow in workflows:
            if not isinstance(workflow, dict):
                continue

            wf_data = {
                "name": workflow.get("name"),
                "description": workflow.get("description"),
                "operations": [],
            }

            for op_ref in workflow.get("operations") or []:
                op_id = op_ref.get("id") if isinstance(op_ref, dict) else None
                operation = self.component_index.get(op_id)

                if not operation or operation.get("type") != 200:
                    continue

                parsed_operation = self._parse_operation(operation)
                wf_data["operations"].append(parsed_operation)

            parsed_workflows.append(wf_data)

        return parsed_workflows

    def _parse_operation(self, operation: dict) -> dict:
        op_data = {
            "name": operation.get("name"),
            "description": operation.get("description"),
            "steps": [],
        }

        steps = operation.get("steps") or operation.get("activities") or []
        if not isinstance(steps, list):
            steps = []

        for index, step_ref in enumerate(steps, start=1):
            if not isinstance(step_ref, dict):
                continue

            step_id = step_ref.get("id") or step_ref.get("activityId")
            step_component = self.component_index.get(step_id)

            if not step_component:
                continue

            parsed_step = self._parse_step(step_component)
            parsed_step["sequence"] = index
            op_data["steps"].append(parsed_step)

        return op_data

    def _parse_step(self, component: dict) -> dict:
        component_type = component.get("type")

        if component_type == 400:
            return self._parse_script(component)
        elif component_type == 500:
            return self._parse_activity(component)
        elif component_type == 700:
            return self._parse_transformation(component)

        return {
            "type": "unknown",
            "name": component.get("name"),
            "raw_type": component_type,
        }

    def _parse_script(self, component: dict) -> dict:
        script_body = ""
        chunks = component.get("chunks")

        if isinstance(chunks, list) and chunks:
            script_body = self._extract_script_from_chunks(component)
        else:
            script_body = (
                component.get("scriptBody")
                or component.get("scriptText")
                or ""
            )

        return {
            "type": "script",
            "name": component.get("name"),
            "description": component.get("description"),
            "script_body": script_body,
            "script_length": len(script_body) if script_body else 0,
        }

    def _parse_activity(self, component: dict) -> dict:
        endpoint_info = self._resolve_endpoint(component)

        adapter_id = component.get("adapterId")
        activity_type = "generic_activity"

        if adapter_id == 13:
            activity_type = "http_activity"
        elif adapter_id == 22:
            activity_type = "variable_activity"

        return {
            "type": activity_type,
            "name": component.get("name"),
            "description": component.get("description"),
            "adapter": adapter_id,
            "endpoint": endpoint_info,
        }

    def _parse_transformation(self, component: dict) -> dict:
        mapping_rules = component.get("mappingRules") or []
        loop_rules = component.get("loopMappingRules") or []

        if not isinstance(mapping_rules, list):
            mapping_rules = []
        if not isinstance(loop_rules, list):
            loop_rules = []

        scripts = []
        conditions = []

        for rule in mapping_rules + loop_rules:
            self._extract_rule_logic(rule, scripts, conditions)

        script_previews = [s[:300] for s in scripts if isinstance(s, str)]

        return {
            "type": "transformation",
            "name": component.get("name"),
            "description": component.get("description"),
            "source_schema": self._get_schema_name(component.get("source")),
            "target_schema": self._get_schema_name(component.get("target")),
            "rule_count": len(mapping_rules) + len(loop_rules),
            "script_count": len(scripts),
            "condition_count": len(conditions),
            "scripts": scripts,
            "script_previews": script_previews,
            "conditions": conditions,
        }

    def _extract_rule_logic(self, rule: dict, scripts: list, conditions: list):
        if not isinstance(rule, dict):
            return

        js = rule.get("script") or rule.get("js") or rule.get("javascript")
        if isinstance(js, str) and js.strip():
            scripts.append(js.strip())

        condition = rule.get("condition") or rule.get("conditionalExpression")
        if isinstance(condition, str) and condition.strip():
            conditions.append(condition.strip())

        children = rule.get("children") or []
        if isinstance(children, list):
            for child in children:
                self._extract_rule_logic(child, scripts, conditions)

    def _get_schema_name(self, schema_obj):
        if isinstance(schema_obj, dict):
            return schema_obj.get("name")
        return None

    def _extract_script_from_chunks(self, component: dict) -> str:
        chunks = component.get("chunks") or []
        if not isinstance(chunks, list):
            return ""

        script_parts = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                text = chunk.get("text")
                if isinstance(text, str):
                    script_parts.append(text)

        return "\n".join(script_parts)

    def _resolve_endpoint(self, component: dict):
        endpoint_ref = component.get("endpoint")
        if not isinstance(endpoint_ref, dict):
            return None

        endpoint = self.component_index.get(endpoint_ref.get("id"))
        if not endpoint:
            return None

        return {
            "name": endpoint.get("name"),
            "adapter": endpoint.get("adapterId"),
            "description": endpoint.get("description"),
        }

    def _find_orphan_operations(self) -> list:
        workflows = self.project.get("workflows") or []

        referenced_op_ids = {
            op.get("id")
            for wf in workflows
            for op in (wf.get("operations") or [])
            if isinstance(op, dict) and op.get("id") is not None
        }

        orphan_ops = []
        for component in self.component_index.values():
            if (
                isinstance(component, dict)
                and component.get("type") == 200
                and component.get("id") not in referenced_op_ids
            ):
                orphan_ops.append(self._parse_operation(component))

        return orphan_ops

    def _parse_all_transformations(self) -> list:
        return [
            self._parse_transformation(component)
            for component in self.component_index.values()
            if isinstance(component, dict) and component.get("type") == 700
        ]
