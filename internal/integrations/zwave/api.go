package zwave

import (
	"fmt"
)

// GetController returns controller information from cache
func (c *Client) GetController() (map[string]interface{}, error) {
	c.stateMu.RLock()
	defer c.stateMu.RUnlock()

	if len(c.controller) == 0 {
		return nil, fmt.Errorf("controller state not yet received")
	}

	// Return a copy to avoid external modification
	result := make(map[string]interface{})
	for k, v := range c.controller {
		result[k] = v
	}
	result["homeId"] = fmt.Sprintf("0x%08x", c.homeID)

	return result, nil
}

// GetNodes returns all Z-Wave nodes from cache
func (c *Client) GetNodes() ([]ZWaveNode, error) {
	c.stateMu.RLock()
	defer c.stateMu.RUnlock()

	// Convert map to slice
	nodes := make([]ZWaveNode, 0, len(c.nodes))
	for _, node := range c.nodes {
		if node != nil {
			nodes = append(nodes, *node)
		}
	}

	return nodes, nil
}

// GetNode returns a specific Z-Wave node from cache
func (c *Client) GetNode(nodeID int) (*ZWaveNode, error) {
	c.stateMu.RLock()
	defer c.stateMu.RUnlock()

	node, ok := c.nodes[nodeID]
	if !ok || node == nil {
		return nil, fmt.Errorf("node %d not found", nodeID)
	}

	// Return a copy
	nodeCopy := *node
	return &nodeCopy, nil
}

// BeginInclusion starts device inclusion
func (c *Client) BeginInclusion(opts InclusionOptions) error {
	args := map[string]interface{}{}
	if opts.Strategy != "" {
		args["strategy"] = opts.Strategy
	}
	if opts.ForceSecurity {
		args["forceSecurity"] = true
	}

	// Correct command:
	_, err := c.Call("controller.begin_inclusion", args)
	return err
}

// StopInclusion stops inclusion
func (c *Client) StopInclusion() error {
	_, err := c.Call("controller.stop_inclusion", nil)
	return err
}

// BeginExclusion starts exclusion
func (c *Client) BeginExclusion() error {
	_, err := c.Call("controller.begin_exclusion", nil)
	return err
}

// StopExclusion stops exclusion
func (c *Client) StopExclusion() error {
	_, err := c.Call("controller.stop_exclusion", nil)
	return err
}

// RemoveFailedNode removes a failed node
func (c *Client) RemoveFailedNode(nodeID int) error {
	_, err := c.Call("controller.remove_failed_node", map[string]interface{}{
		"nodeId": nodeID,
	})
	return err
}

// HealNode performs node heal
func (c *Client) HealNode(nodeID int) error {
	_, err := c.Call("node.heal", map[string]interface{}{
		"nodeId": nodeID,
	})
	return err
}

// SetNodeName sets friendly name
func (c *Client) SetNodeName(nodeID int, name string) error {
	_, err := c.Call("node.set_name", map[string]interface{}{
		"nodeId": nodeID,
		"name":   name,
	})
	return err
}

// SetNodeLocation sets location
func (c *Client) SetNodeLocation(nodeID int, location string) error {
	_, err := c.Call("node.set_location", map[string]interface{}{
		"nodeId":   nodeID,
		"location": location,
	})
	return err
}

// GetValueID gets a value from a node
func (c *Client) GetValueID(nodeID int, valueID ValueID) (interface{}, error) {
	// Correct mapping: node.get_value
	result, err := c.Call("node.get_value", map[string]interface{}{
		"nodeId":       nodeID,
		"commandClass": valueID.CommandClass,
		"property":     valueID.Property,
		"propertyKey":  valueID.PropertyKey,
		"endpoint":     valueID.Endpoint,
	})
	return result, err
}

// SetValueID sets a node value
func (c *Client) SetValueID(nodeID int, valueID ValueID, value interface{}) error {
	// Correct mapping: node.set_value
	_, err := c.Call("node.set_value", map[string]interface{}{
		"nodeId":       nodeID,
		"commandClass": valueID.CommandClass,
		"property":     valueID.Property,
		"propertyKey":  valueID.PropertyKey,
		"endpoint":     valueID.Endpoint,
		"value":        value,
	})
	return err
}

// RefreshValues refreshes node values
func (c *Client) RefreshValues(nodeID int) error {
	// Correct mapping: node.refresh_info
	_, err := c.Call("node.refresh_info", map[string]interface{}{
		"nodeId": nodeID,
	})
	return err
}

// Associations --------------------------------------------------------------

func (c *Client) GetAssociations(nodeID int, group int) ([]int, error) {
	resp, err := c.Call("node.get_associations", map[string]interface{}{
		"nodeId": nodeID,
		"group":  group,
	})
	if err != nil {
		return nil, err
	}

	arr, ok := resp.([]interface{})
	if !ok {
		return []int{}, nil
	}

	var nodes []int
	for _, v := range arr {
		if id, ok := v.(float64); ok {
			nodes = append(nodes, int(id))
		}
	}

	return nodes, nil
}

func (c *Client) AddAssociation(nodeID, group, targetNodeID int) error {
	_, err := c.Call("node.add_associations", map[string]interface{}{
		"nodeId": nodeID,
		"group":  group,
		"associations": []map[string]interface{}{
			{"nodeId": targetNodeID},
		},
	})
	return err
}

func (c *Client) RemoveAssociation(nodeID, group, targetNodeID int) error {
	_, err := c.Call("node.remove_associations", map[string]interface{}{
		"nodeId": nodeID,
		"group":  group,
		"associations": []map[string]interface{}{
			{"nodeId": targetNodeID},
		},
	})
	return err
}

// NVM + Stats ---------------------------------------------------------------

func (c *Client) BackupNVM() error {
	_, err := c.Call("controller.backup_nvm", nil)
	return err
}

func (c *Client) GetStatistics() (map[string]interface{}, error) {
	result, err := c.Call("driver.get_statistics", nil)
	if err != nil {
		return nil, err
	}

	stats, ok := result.(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid statistics response")
	}

	return stats, nil
}
