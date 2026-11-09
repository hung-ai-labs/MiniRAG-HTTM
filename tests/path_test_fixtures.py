class Graph:
    async def get_node(self, name):
        return {'source_id': name.lower(), 'description': 'description ' + name}

    async def get_edge(self, u, v):
        return {'source_id': ''.join(sorted((u, v))).lower()}
