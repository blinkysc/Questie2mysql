#!/usr/bin/env python3
import re
from typing import Dict, List, Any, Optional, Union
import argparse

# MySQL connector is optional if only outputting SQL
mysql_connector_available = True
try:
    import mysql.connector
except ImportError:
    mysql_connector_available = False

def parse_lua_questKeys(lua_content: str) -> Dict[str, int]:
    """Parse the questKeys section to map field names to indices."""
    # Define a default mapping based on WotLK quest field positions
    default_keys = {
        'name': 1,
        'startedBy': 2,
        'finishedBy': 3,
        'requiredLevel': 4,
        'questLevel': 5,
        'requiredRaces': 6,
        'requiredClasses': 7,
        'objectivesText': 8,
        'triggerEnd': 9,
        'objectives': 10,
        'sourceItemId': 11,
        'preQuestGroup': 12,
        'preQuestSingle': 13,
        'childQuests': 14,
        'inGroupWith': 15,
        'exclusiveTo': 16,
        'zoneOrSort': 17,
        'requiredSkill': 18,
        'requiredMinRep': 19,
        'requiredMaxRep': 20,
        'requiredSourceItems': 21,
        'nextQuestInChain': 22,
        'questFlags': 23,
        'specialFlags': 24,
        'parentQuest': 25,
        'reputationReward': 26
    }
    
    # Find the questKeys section
    match = re.search(r"QuestieDB\.questKeys\s*=\s*{(.*?)}", lua_content, re.DOTALL)
    if not match:
        print("Could not find questKeys section, using default mapping")
        return default_keys
    
    quest_keys_str = match.group(1)
    
    # Extract key-value pairs
    pattern = r"\['([^']+)'\]\s*=\s*(\d+)"
    matches = re.findall(pattern, quest_keys_str)
    
    quest_keys = {}
    for key, index in matches:
        quest_keys[key] = int(index)
    
    # Check if we found enough keys
    if len(quest_keys) < 10:
        print(f"Warning: Only found {len(quest_keys)} quest keys, adding default mapping")
        # Add default keys for fields that aren't defined
        for key, index in default_keys.items():
            if key not in quest_keys:
                quest_keys[key] = index
    
    # Debug output
    print(f"Using {len(quest_keys)} quest keys for mapping:")
    for key, index in sorted(quest_keys.items(), key=lambda x: x[1]):
        print(f"  {key}: {index}")
    
    return quest_keys

def extract_quests(lua_content: str) -> Dict[int, List[Any]]:
    """Extract quest data from the LUA file."""
    quests = {}
    
    # Find the quest data section
    match = re.search(r"QuestieDB\.questData\s*=\s*\[\[return\s*{(.*?)}\]\]", lua_content, re.DOTALL)
    if not match:
        raise ValueError("Could not find questData section")
    
    quest_data_str = match.group(1)
    
    # Extract individual quest entries
    for match in re.finditer(r"\[(\d+)\]\s*=\s*{(.*?)},\s*(?=\[\d+\]|\Z)", quest_data_str, re.DOTALL):
        quest_id = int(match.group(1))
        quest_values_str = match.group(2)
        
        # Parse values
        values = []
        buffer = ""
        brace_level = 0
        in_string = False
        escape_next = False
        
        for char in quest_values_str + ',':  # Add a comma to ensure the last value is processed
            if escape_next:
                buffer += char
                escape_next = False
                continue
                
            if char == '\\':
                buffer += char
                escape_next = True
                continue
                
            if char == '"' and not in_string and brace_level == 0:
                in_string = True
                buffer += char
            elif char == '"' and in_string and not escape_next:
                in_string = False
                buffer += char
            elif char == '{' and not in_string:
                brace_level += 1
                buffer += char
            elif char == '}' and not in_string:
                brace_level -= 1
                buffer += char
            elif char == ',' and brace_level == 0 and not in_string:
                values.append(buffer.strip())
                buffer = ""
            else:
                buffer += char
        
        # Convert values to appropriate types
        processed_values = []
        for val in values:
            if val == "nil":
                processed_values.append(None)
            elif val.startswith('"') and val.endswith('"'):
                processed_values.append(val[1:-1])
            elif val.isdigit():
                processed_values.append(int(val))
            elif val.startswith('-') and val[1:].isdigit():
                processed_values.append(int(val))
            else:
                processed_values.append(val)
        
        quests[quest_id] = processed_values
    
    return quests

def create_tables_sql() -> str:
    """Generate SQL statements to create the database tables."""
    sql = []
    
    # Drop existing tables if they exist
    sql.append("DROP TABLE IF EXISTS quest_objectives;")
    sql.append("DROP TABLE IF EXISTS quest_required_items;")
    sql.append("DROP TABLE IF EXISTS quest_relationships;")
    sql.append("DROP TABLE IF EXISTS quest_reputation_rewards;")
    sql.append("DROP TABLE IF EXISTS quest_finishers;")
    sql.append("DROP TABLE IF EXISTS quest_starters;")
    sql.append("DROP TABLE IF EXISTS quest_objective_texts;")
    sql.append("DROP TABLE IF EXISTS quests;")
    
    # Main quests table
    sql.append('''
    CREATE TABLE quests (
        id INT PRIMARY KEY,
        name VARCHAR(255),
        required_level INT,
        quest_level INT,
        required_races INT,
        required_classes INT,
        zone_or_sort INT,
        required_skill_id INT,
        required_skill_value INT,
        required_min_rep_faction INT,
        required_min_rep_value INT,
        required_max_rep_faction INT,
        required_max_rep_value INT,
        source_item_id INT,
        next_quest_in_chain INT,
        quest_flags INT,
        special_flags INT,
        parent_quest INT
    );
    ''')
    
    # Objective texts
    sql.append('''
    CREATE TABLE quest_objective_texts (
        quest_id INT,
        idx INT,
        objective_text TEXT,
        PRIMARY KEY (quest_id, idx),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest starters (NPCs, objects, items)
    sql.append('''
    CREATE TABLE quest_starters (
        quest_id INT,
        starter_type ENUM('creature', 'object', 'item'),
        starter_id INT,
        PRIMARY KEY (quest_id, starter_type, starter_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest finishers (NPCs, objects)
    sql.append('''
    CREATE TABLE quest_finishers (
        quest_id INT,
        finisher_type ENUM('creature', 'object'),
        finisher_id INT,
        PRIMARY KEY (quest_id, finisher_type, finisher_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest reputation rewards
    sql.append('''
    CREATE TABLE quest_reputation_rewards (
        quest_id INT,
        faction_id INT,
        value INT,
        PRIMARY KEY (quest_id, faction_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest relationships (prerequisites, child quests, etc.)
    sql.append('''
    CREATE TABLE quest_relationships (
        quest_id INT,
        relationship_type ENUM('prereq_group', 'prereq_single', 'child', 'in_group', 'exclusive'),
        related_quest_id INT,
        PRIMARY KEY (quest_id, relationship_type, related_quest_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest required items
    sql.append('''
    CREATE TABLE quest_required_items (
        quest_id INT,
        item_id INT,
        PRIMARY KEY (quest_id, item_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    # Quest objectives
    sql.append('''
    CREATE TABLE quest_objectives (
        quest_id INT,
        objective_type ENUM('creature', 'object', 'item', 'reputation', 'killcredit'),
        objective_id INT,
        objective_text VARCHAR(255),
        PRIMARY KEY (quest_id, objective_type, objective_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    );
    ''')
    
    return "\n".join(sql)


def generate_insert_sql(quests: Dict[int, List[Any]], quest_keys: Dict[str, int]) -> str:
    """Generate SQL INSERT statements for all quest data."""
    sql = []
    
    # Define default keys and their positions if they're not found in quest_keys
    default_keys = {
        'name': 1,
        'startedBy': 2,
        'finishedBy': 3,
        'requiredLevel': 4,
        'questLevel': 5,
        'requiredRaces': 6,
        'requiredClasses': 7,
        'objectivesText': 8,
        'triggerEnd': 9,
        'objectives': 10,
        'sourceItemId': 11,
        'preQuestGroup': 12,
        'preQuestSingle': 13,
        'childQuests': 14,
        'inGroupWith': 15,
        'exclusiveTo': 16,
        'zoneOrSort': 17,
        'requiredSkill': 18,
        'requiredMinRep': 19,
        'requiredMaxRep': 20,
        'requiredSourceItems': 21,
        'nextQuestInChain': 22,
        'questFlags': 23,
        'specialFlags': 24,
        'parentQuest': 25,
        'reputationReward': 26
    }
    
    # Use the default keys if they're not found in quest_keys
    for key, value in default_keys.items():
        if key not in quest_keys:
            quest_keys[key] = value
    
    print(f"Using {len(quest_keys)} quest keys for SQL generation")
    
    for quest_id, values in quests.items():
        # Extract basic quest information
        try:
            name = values[quest_keys['name'] - 1] if quest_keys['name'] - 1 < len(values) else None
            required_level = values[quest_keys['requiredLevel'] - 1] if quest_keys['requiredLevel'] - 1 < len(values) else None
            quest_level = values[quest_keys['questLevel'] - 1] if quest_keys['questLevel'] - 1 < len(values) else None
            required_races = values[quest_keys['requiredRaces'] - 1] if quest_keys['requiredRaces'] - 1 < len(values) else None
            required_classes = values[quest_keys['requiredClasses'] - 1] if quest_keys['requiredClasses'] - 1 < len(values) else None
            zone_or_sort = values[quest_keys['zoneOrSort'] - 1] if quest_keys['zoneOrSort'] - 1 < len(values) else None
            
            # Required skill
            required_skill_str = values[quest_keys['requiredSkill'] - 1] if quest_keys['requiredSkill'] - 1 < len(values) else None
            required_skill = extract_nested_array(required_skill_str)
            required_skill_id = required_skill[0] if len(required_skill) > 0 else None
            required_skill_value = required_skill[1] if len(required_skill) > 1 else None
            
            # Required reputation
            required_min_rep_str = values[quest_keys['requiredMinRep'] - 1] if quest_keys['requiredMinRep'] - 1 < len(values) else None
            required_min_rep = extract_nested_array(required_min_rep_str)
            required_min_rep_faction = required_min_rep[0] if len(required_min_rep) > 0 else None
            required_min_rep_value = required_min_rep[1] if len(required_min_rep) > 1 else None
            
            required_max_rep_str = values[quest_keys['requiredMaxRep'] - 1] if quest_keys['requiredMaxRep'] - 1 < len(values) else None
            required_max_rep = extract_nested_array(required_max_rep_str)
            required_max_rep_faction = required_max_rep[0] if len(required_max_rep) > 0 else None
            required_max_rep_value = required_max_rep[1] if len(required_max_rep) > 1 else None
            
            # Other fields
            source_item_id = values[quest_keys['sourceItemId'] - 1] if quest_keys['sourceItemId'] - 1 < len(values) else None
            next_quest_in_chain = values[quest_keys['nextQuestInChain'] - 1] if quest_keys['nextQuestInChain'] - 1 < len(values) else None
            quest_flags = values[quest_keys['questFlags'] - 1] if quest_keys['questFlags'] - 1 < len(values) else None
            special_flags = values[quest_keys['specialFlags'] - 1] if quest_keys['specialFlags'] - 1 < len(values) else None
            parent_quest = values[quest_keys['parentQuest'] - 1] if quest_keys['parentQuest'] - 1 < len(values) else None
            
            # Escape string values
            if name:
                name = name.replace("'", "''")
            
            # Insert basic quest data
            sql.append(f"""
            INSERT INTO quests (
                id, name, required_level, quest_level, required_races, required_classes,
                zone_or_sort, required_skill_id, required_skill_value,
                required_min_rep_faction, required_min_rep_value,
                required_max_rep_faction, required_max_rep_value,
                source_item_id, next_quest_in_chain, quest_flags, special_flags, parent_quest
            ) VALUES (
                {quest_id}, 
                {f"'{name}'" if name is not None else 'NULL'}, 
                {required_level if required_level is not None else 'NULL'}, 
                {quest_level if quest_level is not None else 'NULL'}, 
                {required_races if required_races is not None else 'NULL'}, 
                {required_classes if required_classes is not None else 'NULL'},
                {zone_or_sort if zone_or_sort is not None else 'NULL'}, 
                {required_skill_id if required_skill_id is not None else 'NULL'}, 
                {required_skill_value if required_skill_value is not None else 'NULL'},
                {required_min_rep_faction if required_min_rep_faction is not None else 'NULL'}, 
                {required_min_rep_value if required_min_rep_value is not None else 'NULL'},
                {required_max_rep_faction if required_max_rep_faction is not None else 'NULL'}, 
                {required_max_rep_value if required_max_rep_value is not None else 'NULL'},
                {source_item_id if source_item_id is not None else 'NULL'}, 
                {next_quest_in_chain if next_quest_in_chain is not None else 'NULL'}, 
                {quest_flags if quest_flags is not None else 'NULL'}, 
                {special_flags if special_flags is not None else 'NULL'}, 
                {parent_quest if parent_quest is not None else 'NULL'}
            );
            """)
            
            # Process objective texts
            obj_texts_idx = quest_keys['objectivesText'] - 1
            if obj_texts_idx < len(values) and values[obj_texts_idx]:
                objective_texts = extract_objective_texts(values[obj_texts_idx])
                for idx, text in enumerate(objective_texts):
                    if text:  # Skip empty strings
                        text = text.replace("'", "''")
                        sql.append(f"""
                        INSERT INTO quest_objective_texts (quest_id, idx, objective_text)
                        VALUES ({quest_id}, {idx}, '{text}');
                        """)
            
            # Process starters
            started_by_idx = quest_keys['startedBy'] - 1
            if started_by_idx < len(values) and values[started_by_idx]:
                started_by_str = values[started_by_idx]
                
                # Creature starters
                creature_ids = extract_ids_from_nested_string(started_by_str, 0)
                for creature_id in creature_ids:
                    sql.append(f"""
                    INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                    VALUES ({quest_id}, 'creature', {creature_id});
                    """)
                
                # Object starters
                object_ids = extract_ids_from_nested_string(started_by_str, 1)
                for object_id in object_ids:
                    sql.append(f"""
                    INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                    VALUES ({quest_id}, 'object', {object_id});
                    """)
                
                # Item starters
                item_ids = extract_ids_from_nested_string(started_by_str, 2)
                for item_id in item_ids:
                    sql.append(f"""
                    INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                    VALUES ({quest_id}, 'item', {item_id});
                    """)
            
            # Process finishers
            finished_by_idx = quest_keys['finishedBy'] - 1
            if finished_by_idx < len(values) and values[finished_by_idx]:
                finished_by_str = values[finished_by_idx]
                
                # Creature finishers
                creature_ids = extract_ids_from_nested_string(finished_by_str, 0)
                for creature_id in creature_ids:
                    sql.append(f"""
                    INSERT INTO quest_finishers (quest_id, finisher_type, finisher_id)
                    VALUES ({quest_id}, 'creature', {creature_id});
                    """)
                
                # Object finishers
                object_ids = extract_ids_from_nested_string(finished_by_str, 1)
                for object_id in object_ids:
                    sql.append(f"""
                    INSERT INTO quest_finishers (quest_id, finisher_type, finisher_id)
                    VALUES ({quest_id}, 'object', {object_id});
                    """)
            
            # Process relationships
            # PreQuestGroup
            prequest_group_idx = quest_keys['preQuestGroup'] - 1
            if prequest_group_idx < len(values) and values[prequest_group_idx]:
                prequest_group_str = values[prequest_group_idx]
                prequest_group_ids = extract_nested_array(prequest_group_str)
                for prequest_id in prequest_group_ids:
                    if isinstance(prequest_id, int):
                        sql.append(f"""
                        INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                        VALUES ({quest_id}, 'prereq_group', {prequest_id});
                        """)
            
            # PreQuestSingle
            prequest_single_idx = quest_keys['preQuestSingle'] - 1
            if prequest_single_idx < len(values) and values[prequest_single_idx]:
                prequest_single_str = values[prequest_single_idx]
                prequest_single_ids = extract_nested_array(prequest_single_str)
                for prequest_id in prequest_single_ids:
                    if isinstance(prequest_id, int):
                        sql.append(f"""
                        INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                        VALUES ({quest_id}, 'prereq_single', {prequest_id});
                        """)
            
            # ChildQuests
            child_quests_idx = quest_keys['childQuests'] - 1
            if child_quests_idx < len(values) and values[child_quests_idx]:
                child_quests_str = values[child_quests_idx]
                child_quest_ids = extract_nested_array(child_quests_str)
                for child_id in child_quest_ids:
                    if isinstance(child_id, int):
                        sql.append(f"""
                        INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                        VALUES ({quest_id}, 'child', {child_id});
                        """)
            
            # InGroupWith
            in_group_idx = quest_keys['inGroupWith'] - 1
            if in_group_idx < len(values) and values[in_group_idx]:
                in_group_str = values[in_group_idx]
                in_group_ids = extract_nested_array(in_group_str)
                for group_id in in_group_ids:
                    if isinstance(group_id, int):
                        sql.append(f"""
                        INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                        VALUES ({quest_id}, 'in_group', {group_id});
                        """)
            
            # ExclusiveTo
            exclusive_idx = quest_keys['exclusiveTo'] - 1
            if exclusive_idx < len(values) and values[exclusive_idx]:
                exclusive_str = values[exclusive_idx]
                exclusive_ids = extract_nested_array(exclusive_str)
                for exclusive_id in exclusive_ids:
                    if isinstance(exclusive_id, int):
                        sql.append(f"""
                        INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                        VALUES ({quest_id}, 'exclusive', {exclusive_id});
                        """)
            
            # Process required source items
            req_items_idx = quest_keys['requiredSourceItems'] - 1
            if req_items_idx < len(values) and values[req_items_idx]:
                req_items_str = values[req_items_idx]
                req_item_ids = extract_nested_array(req_items_str)
                for item_id in req_item_ids:
                    if isinstance(item_id, int):
                        sql.append(f"""
                        INSERT INTO quest_required_items (quest_id, item_id)
                        VALUES ({quest_id}, {item_id});
                        """)
            
            # Process reputation rewards
            rep_reward_idx = quest_keys['reputationReward'] - 1
            if rep_reward_idx < len(values) and values[rep_reward_idx]:
                rep_reward_str = values[rep_reward_idx]
                rep_rewards = extract_nested_array(rep_reward_str)
                
                # Each reputation reward should be a pair [faction_id, value]
                for i in range(0, len(rep_rewards), 2):
                    if i+1 < len(rep_rewards):
                        faction_id = rep_rewards[i]
                        rep_value = rep_rewards[i+1]
                        
                        if isinstance(faction_id, int) and isinstance(rep_value, int):
                            sql.append(f"""
                            INSERT INTO quest_reputation_rewards (quest_id, faction_id, value)
                            VALUES ({quest_id}, {faction_id}, {rep_value});
                            """)
            
            # Process objectives
            objectives_idx = quest_keys['objectives'] - 1
            if objectives_idx < len(values) and values[objectives_idx]:
                objectives_str = values[objectives_idx]
                objectives = extract_nested_array(objectives_str)
                
                # Process creature objectives
                if len(objectives) > 0 and objectives[0]:
                    creature_objectives = extract_nested_array(objectives[0])
                    for obj in creature_objectives:
                        if isinstance(obj, list) and len(obj) >= 1:
                            creature_id = obj[0] if isinstance(obj[0], int) else None
                            objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                            
                            if creature_id:
                                if objective_text:
                                    objective_text = objective_text.replace("'", "''")
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'creature', {creature_id}, '{objective_text}');
                                    """)
                                else:
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'creature', {creature_id}, NULL);
                                    """)
                
                # Process object objectives
                if len(objectives) > 1 and objectives[1]:
                    object_objectives = extract_nested_array(objectives[1])
                    for obj in object_objectives:
                        if isinstance(obj, list) and len(obj) >= 1:
                            object_id = obj[0] if isinstance(obj[0], int) else None
                            objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                            
                            if object_id:
                                if objective_text:
                                    objective_text = objective_text.replace("'", "''")
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'object', {object_id}, '{objective_text}');
                                    """)
                                else:
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'object', {object_id}, NULL);
                                    """)
                
                # Process item objectives
                if len(objectives) > 2 and objectives[2]:
                    item_objectives = extract_nested_array(objectives[2])
                    for obj in item_objectives:
                        if isinstance(obj, list) and len(obj) >= 1:
                            item_id = obj[0] if isinstance(obj[0], int) else None
                            objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                            
                            if item_id:
                                if objective_text:
                                    objective_text = objective_text.replace("'", "''")
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'item', {item_id}, '{objective_text}');
                                    """)
                                else:
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'item', {item_id}, NULL);
                                    """)
                
                # Process reputation objectives
                if len(objectives) > 3 and objectives[3]:
                    rep_objective = extract_nested_array(objectives[3])
                    if len(rep_objective) >= 2:
                        faction_id = rep_objective[0] if isinstance(rep_objective[0], int) else None
                        value = rep_objective[1] if isinstance(rep_objective[1], int) else None
                        
                        if faction_id:
                            sql.append(f"""
                            INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                            VALUES ({quest_id}, 'reputation', {faction_id}, '{value}');
                            """)
                
                # Process kill credit objectives
                if len(objectives) > 4 and objectives[4]:
                    killcredit_objectives = extract_nested_array(objectives[4])
                    for obj in killcredit_objectives:
                        if isinstance(obj, list) and len(obj) >= 2:
                            base_creature_id = obj[1] if isinstance(obj[1], int) else None
                            objective_text = obj[2] if len(obj) > 2 and isinstance(obj[2], str) else None
                            
                            if base_creature_id:
                                if objective_text:
                                    objective_text = objective_text.replace("'", "''")
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'killcredit', {base_creature_id}, '{objective_text}');
                                    """)
                                else:
                                    sql.append(f"""
                                    INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                                    VALUES ({quest_id}, 'killcredit', {base_creature_id}, NULL);
                                    """)
        except Exception as e:
            print(f"Error processing quest {quest_id}: {e}")
            # Continue with next quest
    
    return "\n".join(sql)

def extract_objective_texts(obj_texts_str: Optional[Union[str, list]]) -> List[str]:
    """Extract objective texts from a nested array string or list."""
    if obj_texts_str is None:
        return []
    
    # If it's a list, convert string items directly
    if isinstance(obj_texts_str, list):
        return [str(item) if item is not None else "" for item in obj_texts_str]
    
    # If it's not a string, return an empty list
    if not isinstance(obj_texts_str, str):
        return []
    
    if obj_texts_str == "nil":
        return []
    
    # Extract all quoted strings
    return re.findall(r'"([^"]*)"', obj_texts_str)

def extract_nested_array(array_str: Optional[Union[str, list]]) -> List[Any]:
    """Extract a nested array from a string or list."""
    if array_str is None:
        return []
    
    # If it's already a list, return it
    if isinstance(array_str, list):
        return array_str
    
    # If it's not a string, return it wrapped in a list
    if not isinstance(array_str, str):
        return [array_str]
    
    result = []
    if array_str.startswith('{') and array_str.endswith('}'):
        # Remove outer braces
        content = array_str[1:-1].strip()
        if not content:
            return []
        
        # Split by commas, respecting nested structures
        parts = []
        buffer = ""
        brace_level = 0
        in_string = False
        
        for char in content:
            if char == '"':
                in_string = not in_string
            
            if not in_string:
                if char == '{':
                    brace_level += 1
                elif char == '}':
                    brace_level -= 1
                
                if char == ',' and brace_level == 0:
                    parts.append(buffer.strip())
                    buffer = ""
                    continue
            
            buffer += char
        
        if buffer:
            parts.append(buffer.strip())
        
        # Process each part
        for part in parts:
            if part == "nil":
                result.append(None)
            elif part.startswith('{') and part.endswith('}'):
                result.append(extract_nested_array(part))
            elif part.startswith('"') and part.endswith('"'):
                result.append(part[1:-1])
            elif part.isdigit():
                result.append(int(part))
            elif part.startswith('-') and part[1:].isdigit():
                result.append(-int(part[1:]))
            else:
                result.append(part)
    
    return result

def extract_ids_from_nested_string(nested_str: Optional[Union[str, list]], index: int = 0) -> List[int]:
    """Extract IDs from a specific position in a nested string or list."""
    if nested_str is None:
        return []
    
    # For debugging
    # print(f"Extracting IDs from: {nested_str}, type: {type(nested_str)}")
    
    # If it's already a list, extract IDs from it
    if isinstance(nested_str, list):
        # Special case for WotLK triple nested format {{{id}}}
        if len(nested_str) == 1 and isinstance(nested_str[0], list) and len(nested_str[0]) == 1 and isinstance(nested_str[0][0], list):
            return [id for id in nested_str[0][0] if isinstance(id, int)]
            
        # Special case for WotLK double nested format {{id}}
        if len(nested_str) == 1 and isinstance(nested_str[0], list):
            return [id for id in nested_str[0] if isinstance(id, int)]
            
        # Try standard index access
        if index < len(nested_str) and isinstance(nested_str[index], list):
            return [id for id in nested_str[index] if isinstance(id, int)]
            
        # Try to find any integers at any level of nesting
        ids = []
        def find_ints(items):
            for item in items:
                if isinstance(item, int):
                    ids.append(item)
                elif isinstance(item, list):
                    find_ints(item)
        
        find_ints(nested_str)
        return ids
    
    # If it's not a string, return an empty list
    if not isinstance(nested_str, str):
        return []
    
    # For string format, try to parse it
    try:
        # Handle common formats we see in the data
        if nested_str.startswith("{{{") and nested_str.endswith("}}}"):
            # Triple nested: {{{id}}}
            inner = nested_str[3:-3].strip()
            if inner.isdigit():
                return [int(inner)]
        elif nested_str.startswith("{{") and nested_str.endswith("}}"):
            # Double nested: {{id}}
            inner = nested_str[2:-2].strip()
            if inner.isdigit():
                return [int(inner)]
            
        # For more complex structures, use our general extractor
        nested_array = extract_nested_array(nested_str)
        return extract_ids_from_nested_string(nested_array, index)
        
    except Exception as e:
        print(f"Error extracting IDs from string: {e}")
        return []

def insert_quest_data(cursor, quests: Dict[int, List[Any]], quest_keys: Dict[str, int]) -> None:
    """Insert the quest data into MySQL tables."""
    """Insert the quest data into MySQL tables."""
    for quest_id, values in quests.items():
        # Extract basic quest information
        name = values[quest_keys['name'] - 1] if quest_keys['name'] - 1 < len(values) else None
        required_level = values[quest_keys['requiredLevel'] - 1] if quest_keys['requiredLevel'] - 1 < len(values) else None
        quest_level = values[quest_keys['questLevel'] - 1] if quest_keys['questLevel'] - 1 < len(values) else None
        required_races = values[quest_keys['requiredRaces'] - 1] if quest_keys['requiredRaces'] - 1 < len(values) else None
        required_classes = values[quest_keys['requiredClasses'] - 1] if quest_keys['requiredClasses'] - 1 < len(values) else None
        zone_or_sort = values[quest_keys['zoneOrSort'] - 1] if quest_keys['zoneOrSort'] - 1 < len(values) else None
        
        # Required skill
        required_skill_str = values[quest_keys['requiredSkill'] - 1] if quest_keys['requiredSkill'] - 1 < len(values) else None
        required_skill = extract_nested_array(required_skill_str)
        required_skill_id = required_skill[0] if len(required_skill) > 0 else None
        required_skill_value = required_skill[1] if len(required_skill) > 1 else None
        
        # Required reputation
        required_min_rep_str = values[quest_keys['requiredMinRep'] - 1] if quest_keys['requiredMinRep'] - 1 < len(values) else None
        required_min_rep = extract_nested_array(required_min_rep_str)
        required_min_rep_faction = required_min_rep[0] if len(required_min_rep) > 0 else None
        required_min_rep_value = required_min_rep[1] if len(required_min_rep) > 1 else None
        
        required_max_rep_str = values[quest_keys['requiredMaxRep'] - 1] if quest_keys['requiredMaxRep'] - 1 < len(values) else None
        required_max_rep = extract_nested_array(required_max_rep_str)
        required_max_rep_faction = required_max_rep[0] if len(required_max_rep) > 0 else None
        required_max_rep_value = required_max_rep[1] if len(required_max_rep) > 1 else None
        
        # Other fields
        source_item_id = values[quest_keys['sourceItemId'] - 1] if quest_keys['sourceItemId'] - 1 < len(values) else None
        next_quest_in_chain = values[quest_keys['nextQuestInChain'] - 1] if quest_keys['nextQuestInChain'] - 1 < len(values) else None
        quest_flags = values[quest_keys['questFlags'] - 1] if quest_keys['questFlags'] - 1 < len(values) else None
        special_flags = values[quest_keys['specialFlags'] - 1] if quest_keys['specialFlags'] - 1 < len(values) else None
        parent_quest = values[quest_keys['parentQuest'] - 1] if quest_keys['parentQuest'] - 1 < len(values) else None
        
        # Insert basic quest data
        cursor.execute('''
        INSERT INTO quests (
            id, name, required_level, quest_level, required_races, required_classes,
            zone_or_sort, required_skill_id, required_skill_value,
            required_min_rep_faction, required_min_rep_value,
            required_max_rep_faction, required_max_rep_value,
            source_item_id, next_quest_in_chain, quest_flags, special_flags, parent_quest
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            quest_id, name, required_level, quest_level, required_races, required_classes,
            zone_or_sort, required_skill_id, required_skill_value,
            required_min_rep_faction, required_min_rep_value,
            required_max_rep_faction, required_max_rep_value,
            source_item_id, next_quest_in_chain, quest_flags, special_flags, parent_quest
        ))
        
        # Process objective texts
        obj_texts_idx = quest_keys['objectivesText'] - 1
        if obj_texts_idx < len(values) and values[obj_texts_idx]:
            objective_texts = extract_objective_texts(values[obj_texts_idx])
            for idx, text in enumerate(objective_texts):
                if text:  # Skip empty strings
                    cursor.execute('''
                    INSERT INTO quest_objective_texts (quest_id, idx, objective_text)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, idx, text))
        
        # Process starters
        started_by_idx = quest_keys['startedBy'] - 1
        if started_by_idx < len(values) and values[started_by_idx]:
            started_by_str = values[started_by_idx]
            
            # Creature starters
            creature_ids = extract_ids_from_nested_string(started_by_str, 0)
            for creature_id in creature_ids:
                cursor.execute('''
                INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                VALUES (%s, %s, %s)
                ''', (quest_id, 'creature', creature_id))
            
            # Object starters
            object_ids = extract_ids_from_nested_string(started_by_str, 1)
            for object_id in object_ids:
                cursor.execute('''
                INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                VALUES (%s, %s, %s)
                ''', (quest_id, 'object', object_id))
            
            # Item starters
            item_ids = extract_ids_from_nested_string(started_by_str, 2)
            for item_id in item_ids:
                cursor.execute('''
                INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                VALUES (%s, %s, %s)
                ''', (quest_id, 'item', item_id))
        
        # Process finishers
        finished_by_idx = quest_keys['finishedBy'] - 1
        if finished_by_idx < len(values) and values[finished_by_idx]:
            finished_by_str = values[finished_by_idx]
            
            # Creature finishers
            creature_ids = extract_ids_from_nested_string(finished_by_str, 0)
            for creature_id in creature_ids:
                cursor.execute('''
                INSERT INTO quest_finishers (quest_id, finisher_type, finisher_id)
                VALUES (%s, %s, %s)
                ''', (quest_id, 'creature', creature_id))
            
            # Object finishers
            object_ids = extract_ids_from_nested_string(finished_by_str, 1)
            for object_id in object_ids:
                cursor.execute('''
                INSERT INTO quest_finishers (quest_id, finisher_type, finisher_id)
                VALUES (%s, %s, %s)
                ''', (quest_id, 'object', object_id))
        
        # Process relationships
        # PreQuestGroup
        prequest_group_idx = quest_keys['preQuestGroup'] - 1
        if prequest_group_idx < len(values) and values[prequest_group_idx]:
            prequest_group_str = values[prequest_group_idx]
            prequest_group_ids = extract_nested_array(prequest_group_str)
            for prequest_id in prequest_group_ids:
                if isinstance(prequest_id, int):
                    cursor.execute('''
                    INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, 'prereq_group', prequest_id))
        
        # PreQuestSingle
        prequest_single_idx = quest_keys['preQuestSingle'] - 1
        if prequest_single_idx < len(values) and values[prequest_single_idx]:
            prequest_single_str = values[prequest_single_idx]
            prequest_single_ids = extract_nested_array(prequest_single_str)
            for prequest_id in prequest_single_ids:
                if isinstance(prequest_id, int):
                    cursor.execute('''
                    INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, 'prereq_single', prequest_id))
        
        # ChildQuests
        child_quests_idx = quest_keys['childQuests'] - 1
        if child_quests_idx < len(values) and values[child_quests_idx]:
            child_quests_str = values[child_quests_idx]
            child_quest_ids = extract_nested_array(child_quests_str)
            for child_id in child_quest_ids:
                if isinstance(child_id, int):
                    cursor.execute('''
                    INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, 'child', child_id))
        
        # InGroupWith
        in_group_idx = quest_keys['inGroupWith'] - 1
        if in_group_idx < len(values) and values[in_group_idx]:
            in_group_str = values[in_group_idx]
            in_group_ids = extract_nested_array(in_group_str)
            for group_id in in_group_ids:
                if isinstance(group_id, int):
                    cursor.execute('''
                    INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, 'in_group', group_id))
        
        # ExclusiveTo
        exclusive_idx = quest_keys['exclusiveTo'] - 1
        if exclusive_idx < len(values) and values[exclusive_idx]:
            exclusive_str = values[exclusive_idx]
            exclusive_ids = extract_nested_array(exclusive_str)
            for exclusive_id in exclusive_ids:
                if isinstance(exclusive_id, int):
                    cursor.execute('''
                    INSERT INTO quest_relationships (quest_id, relationship_type, related_quest_id)
                    VALUES (%s, %s, %s)
                    ''', (quest_id, 'exclusive', exclusive_id))
        
        # Process required source items
        req_items_idx = quest_keys['requiredSourceItems'] - 1
        if req_items_idx < len(values) and values[req_items_idx]:
            req_items_str = values[req_items_idx]
            req_item_ids = extract_nested_array(req_items_str)
            for item_id in req_item_ids:
                if isinstance(item_id, int):
                    cursor.execute('''
                    INSERT INTO quest_required_items (quest_id, item_id)
                    VALUES (%s, %s)
                    ''', (quest_id, item_id))
        
        # Process reputation rewards
        rep_reward_idx = quest_keys['reputationReward'] - 1
        if rep_reward_idx < len(values) and values[rep_reward_idx]:
            rep_reward_str = values[rep_reward_idx]
            rep_rewards = extract_nested_array(rep_reward_str)
            
            # Each reputation reward should be a pair [faction_id, value]
            for i in range(0, len(rep_rewards), 2):
                if i+1 < len(rep_rewards):
                    faction_id = rep_rewards[i]
                    rep_value = rep_rewards[i+1]
                    
                    if isinstance(faction_id, int) and isinstance(rep_value, int):
                        cursor.execute('''
                        INSERT INTO quest_reputation_rewards (quest_id, faction_id, value)
                        VALUES (%s, %s, %s)
                        ''', (quest_id, faction_id, rep_value))
        
        # Process objectives
        objectives_idx = quest_keys['objectives'] - 1
        if objectives_idx < len(values) and values[objectives_idx]:
            objectives_str = values[objectives_idx]
            objectives = extract_nested_array(objectives_str)
            
            # Process creature objectives
            if len(objectives) > 0 and objectives[0]:
                creature_objectives = extract_nested_array(objectives[0])
                for obj in creature_objectives:
                    if isinstance(obj, list) and len(obj) >= 1:
                        creature_id = obj[0] if isinstance(obj[0], int) else None
                        objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                        
                        if creature_id:
                            cursor.execute('''
                            INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                            VALUES (%s, %s, %s, %s)
                            ''', (quest_id, 'creature', creature_id, objective_text))
            
            # Process object objectives
            if len(objectives) > 1 and objectives[1]:
                object_objectives = extract_nested_array(objectives[1])
                for obj in object_objectives:
                    if isinstance(obj, list) and len(obj) >= 1:
                        object_id = obj[0] if isinstance(obj[0], int) else None
                        objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                        
                        if object_id:
                            cursor.execute('''
                            INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                            VALUES (%s, %s, %s, %s)
                            ''', (quest_id, 'object', object_id, objective_text))
            
            # Process item objectives
            if len(objectives) > 2 and objectives[2]:
                item_objectives = extract_nested_array(objectives[2])
                for obj in item_objectives:
                    if isinstance(obj, list) and len(obj) >= 1:
                        item_id = obj[0] if isinstance(obj[0], int) else None
                        objective_text = obj[1] if len(obj) > 1 and isinstance(obj[1], str) else None
                        
                        if item_id:
                            cursor.execute('''
                            INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                            VALUES (%s, %s, %s, %s)
                            ''', (quest_id, 'item', item_id, objective_text))
            
            # Process reputation objectives
            if len(objectives) > 3 and objectives[3]:
                rep_objective = extract_nested_array(objectives[3])
                if len(rep_objective) >= 2:
                    faction_id = rep_objective[0] if isinstance(rep_objective[0], int) else None
                    value = rep_objective[1] if isinstance(rep_objective[1], int) else None
                    
                    if faction_id:
                        cursor.execute('''
                        INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                        VALUES (%s, %s, %s, %s)
                        ''', (quest_id, 'reputation', faction_id, str(value)))
            
            # Process kill credit objectives
            if len(objectives) > 4 and objectives[4]:
                killcredit_objectives = extract_nested_array(objectives[4])
                for obj in killcredit_objectives:
                    if isinstance(obj, list) and len(obj) >= 2:
                        base_creature_id = obj[1] if isinstance(obj[1], int) else None
                        objective_text = obj[2] if len(obj) > 2 and isinstance(obj[2], str) else None
                        
                        if base_creature_id:
                            cursor.execute('''
                            INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                            VALUES (%s, %s, %s, %s)
                            ''', (quest_id, 'killcredit', base_creature_id, objective_text))

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Convert Questie Lua database to MySQL')
    parser.add_argument('--input', required=True, help='Input Lua file path')
    parser.add_argument('--host', default='localhost', help='MySQL host (default: localhost)')
    parser.add_argument('--user', help='MySQL username')
    parser.add_argument('--password', help='MySQL password')
    parser.add_argument('--database', help='MySQL database name')
    parser.add_argument('--port', type=int, default=3306, help='MySQL port (default: 3306)')
    parser.add_argument('--output', help='Output SQL file path (if not connecting to a database)')
    parser.add_argument('--stdout', action='store_true', help='Output SQL to stdout (instead of connecting to a database)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--inspect', type=int, help='Inspect a specific quest ID')
    parser.add_argument('--test-nested', type=int, help='Test nested structure parsing for a specific quest ID')
    
    args = parser.parse_args()
    
    try:
        # Read the input file
        with open(args.input, 'r', encoding='utf-8') as f:
            lua_content = f.read()
        
        # Parse questKeys
        quest_keys = parse_lua_questKeys(lua_content)
        
        # Extract quest data
        quests = extract_quests(lua_content)
        
        print(f"Parsed {len(quests)} quests from Lua file")
        
        # If testing nested structure parsing
        if args.test_nested:
            if args.test_nested in quests:
                quest_id = args.test_nested
                quest_data = quests[quest_id]
                print(f"\nTesting nested structure parsing for quest ID {quest_id}:")
                
                # Test starter NPCs
                started_by_idx = quest_keys['startedBy'] - 1
                if started_by_idx < len(quest_data) and quest_data[started_by_idx]:
                    started_by_str = quest_data[started_by_idx]
                    print(f"\nField {started_by_idx+1} (startedBy): {started_by_str}")
                    
                    # Extract creature starters
                    creature_ids = extract_ids_from_nested_string(started_by_str, 0)
                    print(f"  Extracted starter NPCs: {creature_ids}")
                    
                    # Generate SQL for each
                    for creature_id in creature_ids:
                        sql = f"""
                        INSERT INTO quest_starters (quest_id, starter_type, starter_id)
                        VALUES ({quest_id}, 'creature', {creature_id});
                        """
                        print(f"  SQL: {sql.strip()}")
                
                # Test finisher NPCs
                finished_by_idx = quest_keys['finishedBy'] - 1
                if finished_by_idx < len(quest_data) and quest_data[finished_by_idx]:
                    finished_by_str = quest_data[finished_by_idx]
                    print(f"\nField {finished_by_idx+1} (finishedBy): {finished_by_str}")
                    
                    # Extract creature finishers
                    creature_ids = extract_ids_from_nested_string(finished_by_str, 0)
                    print(f"  Extracted finisher NPCs: {creature_ids}")
                    
                    # Generate SQL for each
                    for creature_id in creature_ids:
                        sql = f"""
                        INSERT INTO quest_finishers (quest_id, finisher_type, finisher_id)
                        VALUES ({quest_id}, 'creature', {creature_id});
                        """
                        print(f"  SQL: {sql.strip()}")
                
                # Test objectives
                objectives_idx = quest_keys['objectives'] - 1
                if objectives_idx < len(quest_data) and quest_data[objectives_idx]:
                    objectives_str = quest_data[objectives_idx]
                    print(f"\nField {objectives_idx+1} (objectives): {objectives_str}")
                    
                    # Parse the objectives data
                    objectives = extract_nested_array(objectives_str)
                    print(f"  Parsed objectives: {objectives}")
                    
                    # Try to extract creature objectives
                    creature_ids = extract_ids_from_nested_string(objectives_str, 0)
                    print(f"  Extracted creature objectives: {creature_ids}")
                    
                    # Generate SQL for each
                    for creature_id in creature_ids:
                        sql = f"""
                        INSERT INTO quest_objectives (quest_id, objective_type, objective_id, objective_text)
                        VALUES ({quest_id}, 'creature', {creature_id}, NULL);
                        """
                        print(f"  SQL: {sql.strip()}")
            else:
                print(f"Quest ID {args.test_nested} not found in the database")
            # Exit after testing
            return
        
        # If inspecting a specific quest, dump its data
        if args.inspect:
            if args.inspect in quests:
                quest_id = args.inspect
                print(f"\nInspecting quest ID {quest_id}:")
                quest_data = quests[quest_id]
                print(f"Number of fields: {len(quest_data)}")
                
                # Create a field name map, avoiding sub-fields
                field_name_map = {}
                for k, v in quest_keys.items():
                    # Skip sub-fields like 'creatureStart'
                    if k not in ['creatureStart', 'objectStart', 'itemStart', 'creatureEnd', 'objectEnd']:
                        field_name_map[v-1] = k
                
                for i, value in enumerate(quest_data):
                    field_name = field_name_map.get(i, f"Field {i+1}")
                    print(f"{field_name} ({i+1}): {value}")
                    
                    # For nested structures, try to extract the actual values
                    if isinstance(value, list) or (isinstance(value, str) and (value.startswith('{{') or value.startswith('{{{'))):
                        extracted_ids = extract_ids_from_nested_string(value)
                        if extracted_ids:
                            print(f"  Extracted values: {extracted_ids}")
                
                # Show quest data in tabular format
                print("\nQuest Data Summary:")
                print(f"ID: {quest_id}")
                print(f"Name: {quest_data[quest_keys['name']-1]}")
                print(f"Required Level: {quest_data[quest_keys['requiredLevel']-1]}")
                print(f"Quest Level: {quest_data[quest_keys['questLevel']-1]}")
                print(f"Required Races: {quest_data[quest_keys['requiredRaces']-1]}")
                
                # Show NPCs
                started_by = extract_ids_from_nested_string(quest_data[quest_keys['startedBy']-1])
                finished_by = extract_ids_from_nested_string(quest_data[quest_keys['finishedBy']-1])
                print(f"Started By NPCs: {started_by}")
                print(f"Finished By NPCs: {finished_by}")
                
                # Show objectives if available
                if quest_keys['objectives']-1 < len(quest_data) and quest_data[quest_keys['objectives']-1]:
                    objectives = extract_ids_from_nested_string(quest_data[quest_keys['objectives']-1])
                    print(f"Objectives: {objectives}")
            else:
                print(f"Quest ID {args.inspect} not found in the database")
            # Exit after inspection
            return
        
        # Validate arguments for database operations
        if not ((args.user and args.password and args.database) or args.output or args.stdout):
            print("Error: Either database credentials (--user, --password, --database) or --output or --stdout must be provided")
            return
        
        # Determine output mode
        if args.stdout or args.output:
            # Generate SQL statements
            sql = create_tables_sql() + "\n\n" + generate_insert_sql(quests, quest_keys)
            
            if args.stdout:
                # Output to stdout
                print(sql)
            else:
                # Output to file
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(sql)
                print(f"SQL statements written to {args.output}")
        else:
            # Check if mysql.connector is available
            if not mysql_connector_available:
                print("Error: MySQL Connector is required for direct database connection.")
                print("Please install it with: pip install mysql-connector-python")
                print("Alternatively, use --output or --stdout to generate SQL without connecting to a database.")
                return
                
            # Connect to MySQL and import directly
            conn = mysql.connector.connect(
                host=args.host,
                user=args.user,
                password=args.password,
                database=args.database,
                port=args.port
            )
            
            cursor = conn.cursor()
            
            # Create the tables
            create_tables(cursor)
            
            # Insert the data
            insert_quest_data(cursor, quests, quest_keys)
            
            # Commit the changes
            conn.commit()
            
            print(f"Successfully imported {len(quests)} quests into MySQL database")
            
            cursor.close()
            conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals() and mysql_connector_available and conn.is_connected():
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    main()