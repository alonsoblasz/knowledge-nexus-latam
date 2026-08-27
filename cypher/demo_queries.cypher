// 1. Conteo general para auditar la carga.
MATCH (n:Entity)
RETURN n.entity_type AS entity_type, count(*) AS records
ORDER BY entity_type;

// 2. Relaciones explícitas de una necesidad, proyecto u otra entidad.
MATCH (source:Entity {id: $entity_id})-[relationship]-(target:Entity)
RETURN source.id AS source_id,
       type(relationship) AS relationship,
       target.id AS target_id,
       target.entity_type AS target_type,
       target.title AS target_title,
       relationship.provenance_json AS provenance
ORDER BY relationship, target_id;

// 3. Proyecto -> investigadores -> expertise.
MATCH (researcher:Researcher)-[participation:PARTICIPATED_IN_PROJECT]->
      (project:Project {id: $project_id})
OPTIONAL MATCH (researcher)-[:HAS_EXPERTISE]->(expertise:Expertise)
RETURN project.id AS project_id,
       researcher.id AS researcher_id,
       researcher.title AS researcher,
       participation.role AS project_role,
       collect(DISTINCT expertise.title) AS expertise
ORDER BY researcher;

// 4. Proyecto -> grupo -> líneas de investigación.
MATCH (project:Project {id: $project_id})-[:EXECUTED_BY_GROUP]->(group:ResearchGroup)
OPTIONAL MATCH (line:ResearchLine)-[:BELONGS_TO_GROUP]->(group)
RETURN project.id AS project_id,
       group.id AS group_id,
       group.title AS research_group,
       collect(DISTINCT {id: line.id, title: line.title}) AS research_lines;

// 5. Documento complementario y procedencia de una entidad.
MATCH (document:Document)-[:DESCRIBES]->(entity:Entity {id: $entity_id})
RETURN entity.id AS entity_id,
       entity.source_file AS csv_file,
       entity.source_row AS csv_row,
       document.file_name AS document_file,
       document.content AS document_content;

// 6. Línea base léxica. Útil para comparar contra búsqueda vectorial.
CALL db.index.fulltext.queryNodes('semantic_text_fulltext', $query_text)
YIELD node, score
WHERE node.entity_type IN $target_types
RETURN node.id AS id,
       node.entity_type AS entity_type,
       node.title AS title,
       score
ORDER BY score DESC
LIMIT $limit;

// 7. Búsqueda vectorial. Requiere que el frente de búsqueda escriba n.embedding.
CALL db.index.vector.queryNodes('semantic_embedding', $limit, $query_embedding)
YIELD node, score
WHERE node.entity_type IN $target_types
RETURN node.id AS id,
       node.entity_type AS entity_type,
       node.title AS title,
       score,
       node.source_file AS source_file,
       node.source_row AS source_row
ORDER BY score DESC;

