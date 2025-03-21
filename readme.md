# Questie Lua to MySQL Converter

A Python utility that converts the Questie Lua database (used by the World of Warcraft addon) into a structured MySQL database.

## Overview

The Questie addon for World of Warcraft stores quest data in Lua files. This tool parses those Lua files and converts them to a relational MySQL database schema, making it easier to query and analyze quest data.

## Features

- Parses Questie Lua database files from different WoW versions (Classic, TBC, WotLK)
- Creates a normalized database schema with appropriate tables and relationships
- Handles complex nested data structures
- Provides detailed inspection and testing capabilities for data validation
- Can output SQL directly to a file or to stdout for piping to mysql
- Direct MySQL import capability (requires mysql-connector-python)

## Installation

### Prerequisites

- Python 3.6 or higher
- (Optional) MySQL server for importing the data
- (Optional) mysql-connector-python package for direct database connections

### Setup

1. Clone this repository or download the `questie-converter.py` script.

2. (Optional) Install the MySQL connector if you want to connect directly to a database:
   ```
   pip install mysql-connector-python
   ```

## Usage

### Basic Usage

Generate SQL file from a Questie database:

```bash
python3 questie-converter.py --input path/to/questieDB.lua --output output.sql
```

Print SQL to stdout:

```bash
python3 questie-converter.py --input path/to/questieDB.lua --stdout
```

Import directly to a MySQL database:

```bash
python3 questie-converter.py --input path/to/questieDB.lua --user myuser --password mypass --database wow_quests
```

### Command-line Options

```
--input PATH            Input Lua file path (required)
--output PATH           Output SQL file path
--stdout                Output SQL to stdout instead of a file
--user USERNAME         MySQL username
--password PASSWORD     MySQL password
--database NAME         MySQL database name
--host HOST             MySQL host (default: localhost)
--port PORT             MySQL port (default: 3306)
--debug                 Enable debug output
--inspect ID            Inspect a specific quest ID
--test-nested ID        Test nested structure parsing for a specific quest ID
```

### Inspection and Debugging

Inspect a specific quest:

```bash
python3 questie-converter.py --input path/to/questieDB.lua --inspect 26034
```

Test nested structure parsing:

```bash
python3 questie-converter.py --input path/to/questieDB.lua --test-nested 26034
```

## Database Schema

The script creates the following tables:

1. **quests**: Main quest information (ID, name, level, requirements, etc.)
2. **quest_objective_texts**: Quest objective text descriptions
3. **quest_starters**: NPCs, objects, or items that start quests
4. **quest_finishers**: NPCs or objects that complete quests
5. **quest_reputation_rewards**: Reputation rewards for completing quests
6. **quest_relationships**: Quest prerequisite and chain relationships
7. **quest_required_items**: Items needed for quests
8. **quest_objectives**: Required objectives to complete quests

## Examples

### Export Quest Data to SQL File

```bash
python3 questie-converter.py --input wotlkQuestDB.lua --output wotlk_quests.sql
```

### Import Directly to Database

```bash
python3 questie-converter.py --input classicQuestDB.lua --user root --password mypass --database wow_classic
```

### Pipe to MySQL Command Line

```bash
python3 questie-converter.py --input tbcQuestDB.lua --stdout | mysql -u username -p database_name
```

## Troubleshooting

### Missing Modules

If you see an error like:
```
ModuleNotFoundError: No module named 'mysql'
```

You can either:
1. Install the required module: `pip install mysql-connector-python`
2. Use file output instead with `--output` or `--stdout`

### Nested Structure Issues

If you encounter issues with nested data structures (like `{{id}}` or `{{{id}}}`), try using the `--test-nested` option to debug a specific quest:

```bash
python3 questie-converter.py --input questDB.lua --test-nested 26034
```

### Structure of Quest Data

WotLK quest data has a specific structure with fields including:
- Field 1: Quest name
- Field 2: Quest starter NPCs (in format {{id}})
- Field 3: Quest finisher NPCs (in format {{id}})
- Field 4: Required level
- Field 5: Quest level
- Fields 6-7: Race and class requirements
- Field 8: Objective text
- Field 10: Objectives (in format {{{id}}})
- Field 17: Zone ID
- Field 23: Quest flags

The script handles these specialized nested formats to extract the correct IDs.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- The Questie addon team for their work on documenting WoW quest data
- Contributors to the WoW database documentation